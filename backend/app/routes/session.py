from datetime import datetime

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import ValidationError
from sqlalchemy import update

from app.extensions import db
from app.db_models import (
    Student,
    Module,
    ModuleContent,
    ModuleMilestoneItem,
    Enrollment,
    LearningSession,
    DistractionEvent,
    InterventionLog,
    GuardianConsent,
    SystemSetting,
    InterventionConfig,
    MilestoneQuestion,
)
from app.schemas.session_schema import (
    SessionStartSchema,
    HeartbeatSchema,
    InterventionResponseSchema,
    TriggerInterventionSchema,
)
from app.services.intervention_engine import (
    InterventionEngine,
    TYPE_HINT,
    TYPE_MILESTONE,
    TYPE_NOISE_NOTICE,
)
from app.services.ml_service import MLService
from app.services.noise_monitor import NoiseMonitor
from app.services.focus_metrics import compute_session_focus_percentage
from app.utils.decorators import role_required

session_bp = Blueprint("session", __name__)

# In-memory registry of active session intervention engines keyed by session_id
SESSION_ENGINES = {}

# Per-session background-noise monitors keyed by session_id
SESSION_NOISE_MONITORS = {}

# Postgres enum monitoring_verdict is lowercase; API/ML stay UPPERCASE.
DB_DISTRACTED = "distracted"
DB_FOCUSED = "focused"


def format_validation_errors(err: ValidationError):
    details = []
    for e in err.errors():
        field = "->".join(str(x) for x in e["loc"]) if e["loc"] else "body"
        details.append({"field": field, "message": e["msg"]})
    return details


def _get_cooldown_seconds() -> float:
    row = SystemSetting.query.filter_by(key="intervention_min_cooldown_seconds").first()
    try:
        return float(row.value) if row else 30.0
    except (TypeError, ValueError):
        return 30.0


def _get_enabled_tiers(subject_id: int):
    cfg = InterventionConfig.query.filter_by(subject_id=subject_id).first()
    if not cfg:
        return [1, 2, 3, 4]
    # Preserve an explicit empty list (all tiers disabled). Do not coerce to [1..4].
    return cfg.enabled_tiers()


def claim_session_xp_award(session_id: int) -> bool:
    """
    Atomically claim the one-time session XP award.

    Returns True only for the caller that flipped xp_awarded from False→True.
    Safe under concurrent stop requests (UPDATE ... WHERE xp_awarded = false).
    """
    result = db.session.execute(
        update(LearningSession)
        .where(
            LearningSession.id == session_id,
            LearningSession.xp_awarded.is_(False),
        )
        .values(xp_awarded=True)
    )
    db.session.commit()
    return int(result.rowcount or 0) == 1


def _build_engine(subject_id: int) -> InterventionEngine:
    return InterventionEngine(
        cooldown_seconds=_get_cooldown_seconds(),
        enabled_tiers=_get_enabled_tiers(subject_id),
    )


def get_open_distraction_event(session_id: int):
    return (
        DistractionEvent.query.filter_by(session_id=session_id, verdict=DB_DISTRACTED)
        .filter(DistractionEvent.ended_at.is_(None))
        .order_by(DistractionEvent.started_at.desc())
        .first()
    )


def upsert_distraction_episode(session_id: int, verdict: str, confidence: float, now_dt: datetime):
    """
    Open-episode semantics:
      DISTRACTED + no open → create
      DISTRACTED + open → keep open
      FOCUSED + open → close with ended_at
    Returns (open_or_closed_event, just_closed: bool)

    `verdict` is the API/ML uppercase value; DB rows use lowercase enum values.
    """
    open_event = get_open_distraction_event(session_id)

    if verdict == "DISTRACTED":
        if open_event:
            open_event.confidence = confidence if confidence is not None else open_event.confidence
            db.session.commit()
            return open_event, False
        event = DistractionEvent(
            session_id=session_id,
            verdict=DB_DISTRACTED,
            confidence=confidence if confidence is not None else 0.0,
            started_at=now_dt,
        )
        db.session.add(event)
        db.session.commit()
        return event, False

    if open_event:
        open_event.ended_at = now_dt
        db.session.commit()
        return open_event, True
    return None, False


def _resolve_module_and_content_ids(session: LearningSession):
    """LearningSession.module_id stores Module.id. Returns (module_id, None)."""
    module = db.session.get(Module, session.module_id)
    if module:
        return module.id, None
    return None, None


def _pick_milestone_item(session: LearningSession):
    module_id, _content_id = _resolve_module_and_content_ids(session)
    if not module_id:
        return None
    content_ids = [
        c.id for c in ModuleContent.query.filter_by(module_id=module_id).all()
    ]
    if not content_ids:
        return None
    return (
        ModuleMilestoneItem.query.filter(
            ModuleMilestoneItem.is_active.is_(True),
            ModuleMilestoneItem.module_content_id.in_(content_ids),
        )
        .order_by(ModuleMilestoneItem.sequence_order.asc())
        .first()
    )


def _enrich_milestone_payload(session: LearningSession, payload: dict) -> dict:
    """Build client-safe milestone payload (no correct_option) + server grading fields."""
    payload = dict(payload or {})
    item = _pick_milestone_item(session)
    if item:
        payload.update(
            {
                "milestone_item_id": item.id,
                "generated_question": item.question,
                "options": list(item.options_json or []),
                "hint_text": item.hint_text,
            }
        )
        payload["_server_correct_option"] = int(item.correct_option)
    else:
        payload.setdefault(
            "generated_question",
            "What is the main idea of this material?",
        )
        payload.setdefault(
            "options",
            [
                "The core concept from the lesson",
                "An unrelated topic",
                "A homework deadline",
                "None of the above",
            ],
        )
        payload.setdefault("hint_text", "Skim the summary for the key idea.")
        payload["_server_correct_option"] = int(payload.get("correct_option", 0) or 0)
    payload.pop("correct_option", None)
    return payload


def _client_milestone_payload(payload: dict) -> dict:
    safe = dict(payload or {})
    safe.pop("_server_correct_option", None)
    safe.pop("correct_option", None)
    return safe


def _persist_triggered_intervention(session, triggered, distraction_event_id, now_dt):
    """Create InterventionLog (+ MilestoneQuestion for quiz/milestone types) and return API dict."""
    log_entry = InterventionLog(
        session_id=session.id,
        distraction_event_id=distraction_event_id,
        triggered_at=now_dt,
        tier=triggered.tier,
        intervention_type=triggered.intervention_type,
    )
    db.session.add(log_entry)
    db.session.flush()

    payload = dict(triggered.payload or {})
    if triggered.intervention_type == TYPE_MILESTONE:
        payload = _enrich_milestone_payload(session, payload)
        server_correct = payload.pop("_server_correct_option", None)
        mq = MilestoneQuestion(
            intervention_id=log_entry.id,
            generated_question=payload.get("generated_question", ""),
            hint_text=payload.get("hint_text"),
            milestone_item_id=payload.get("milestone_item_id"),
            correct_option=server_correct,
        )
        db.session.add(mq)
        db.session.commit()
        payload["milestone_question_id"] = mq.id
        payload["generated_question"] = mq.generated_question
        payload["hint_text"] = mq.hint_text
        payload = _client_milestone_payload(payload)
    elif triggered.intervention_type == TYPE_HINT:
        mq = MilestoneQuestion(
            intervention_id=log_entry.id,
            generated_question=payload.get(
                "generated_question",
                "What is the main idea of the section you just read?",
            ),
            hint_text=payload.get(
                "hint_text",
                "Skim the heading and first sentence of the current section.",
            ),
        )
        db.session.add(mq)
        db.session.commit()
        payload["milestone_question_id"] = mq.id
        payload["generated_question"] = mq.generated_question
        payload["hint_text"] = mq.hint_text
        payload = _client_milestone_payload(payload)
    else:
        db.session.commit()
        payload = _client_milestone_payload(payload)

    return {
        "intervention_id": log_entry.id,
        "tier": triggered.tier,
        "intervention_type": triggered.intervention_type,
        "message": triggered.message,
        "triggered_at": now_dt.isoformat(),
        "payload": payload,
    }


@session_bp.route("/start", methods=["POST"])
@jwt_required()
@role_required("student")
def start_session():
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = SessionStartSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    module = db.session.get(Module, data.module_id)
    if not module or module.is_archived:
        return jsonify({"error": "Module not found or is archived"}), 404

    enrollment = Enrollment.query.filter_by(student_id=student.id, subject_id=module.subject_id).first()
    if not enrollment:
        return jsonify({"error": "Forbidden: You are not enrolled in the course for this module"}), 403

    if data.is_monitored:
        consent = GuardianConsent.query.filter_by(student_id=student.id).first()
        if not consent or not consent.consent_given:
            return jsonify({"error": "Parental/Guardian consent required for monitored learning sessions"}), 403

    active_sessions = LearningSession.query.filter_by(student_id=student.id, end_time=None).all()
    now_dt = datetime.utcnow()
    for s in active_sessions:
        s.end_time = now_dt
        open_ev = get_open_distraction_event(s.id)
        if open_ev:
            open_ev.ended_at = now_dt
        if s.id in SESSION_ENGINES:
            del SESSION_ENGINES[s.id]
        SESSION_NOISE_MONITORS.pop(s.id, None)

    new_session = LearningSession(
        student_id=student.id,
        module_id=module.id,
        start_time=now_dt,
        is_monitored=data.is_monitored,
    )
    db.session.add(new_session)
    db.session.commit()

    SESSION_ENGINES[new_session.id] = _build_engine(module.subject_id)
    SESSION_NOISE_MONITORS[new_session.id] = NoiseMonitor()

    return jsonify({
        "message": "Learning session started successfully",
        "session_id": new_session.id,
        "student_id": student.id,
        "module_id": module.id,
        "start_time": new_session.start_time.isoformat(),
        "is_monitored": new_session.is_monitored,
    }), 201


@session_bp.route("/<int:session_id>/heartbeat", methods=["POST"])
@jwt_required()
@role_required("student")
def send_heartbeat(session_id):
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    session = db.session.get(LearningSession, session_id)
    if not session or session.student_id != student.id:
        return jsonify({"error": "Learning session not found"}), 404

    if session.end_time is not None:
        return jsonify({"error": "This learning session has already ended"}), 400

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = HeartbeatSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    now_dt = datetime.utcnow()
    ml_service = MLService()
    verdict = None
    confidence = data.confidence
    gaze_label = data.gaze_label
    engagement_score = data.engagement_score
    ml_mode = None
    ml_features = {}

    if data.image:
        ml_verdict, ml_conf, ml_features = ml_service.predict_frame_image(
            data.image, session_id=session.id
        )
        verdict = ml_verdict
        confidence = ml_conf
        gaze_label = ml_features.get("gaze_label", gaze_label)
        engagement_score = ml_features.get("engagement_score", engagement_score)
        ml_mode = ml_features.get("ml_mode") or ml_service.ml_mode
    elif data.features:
        verdict, confidence = ml_service.predict_window_features(data.features)
    elif current_app.config.get("TESTING") and data.verdict:
        # Unit tests exercise the intervention engine without ML frames
        verdict = data.verdict
        confidence = data.confidence if data.confidence is not None else 1.0
    else:
        return jsonify({
            "error": "Webcam frame (image) or features required for heartbeat telemetry"
        }), 400

    episode, just_closed = upsert_distraction_episode(
        session.id, verdict, confidence if confidence is not None else 0.0, now_dt
    )

    intervention_data = None
    noise_monitor = None
    noise_triggered = False
    if session.is_monitored:
        module = db.session.get(Module, session.module_id)
        subject_id = module.subject_id if module else None
        if session.id not in SESSION_ENGINES:
            SESSION_ENGINES[session.id] = _build_engine(subject_id) if subject_id else InterventionEngine()
        if session.id not in SESSION_NOISE_MONITORS:
            SESSION_NOISE_MONITORS[session.id] = NoiseMonitor()

        engine = SESSION_ENGINES[session.id]
        noise_monitor = SESSION_NOISE_MONITORS[session.id]
        is_distracted = verdict == "DISTRACTED"
        open_episode = episode if is_distracted and not just_closed else None

        triggered = engine.decide_intervention(
            distraction_event=open_episode,
            is_distracted=is_distracted,
            is_quiz_context=bool(data.is_quiz_context),
            wall_now=now_dt,
        )
        triggered_event_id = open_episode.id if open_episode else None

        # Background noise is a separate, gentler signal: it never opens a
        # distraction episode or changes the ML verdict, and the visual
        # intervention (already computed above) always wins the slot.
        noise_should_fire = noise_monitor.update(
            data.noise_dbfs,
            lesson_audio_active=bool(data.lesson_audio_active),
        )
        if triggered is None and noise_should_fire:
            triggered = engine.consider_noise(
                noise_dbfs=data.noise_dbfs,
                baseline_dbfs=noise_monitor.baseline_dbfs,
            )
            if triggered is not None:
                noise_triggered = True
                triggered_event_id = None

        if triggered:
            intervention_data = _persist_triggered_intervention(
                session,
                triggered,
                triggered_event_id,
                now_dt,
            )
            if noise_triggered:
                # The one-per-session notice is now actually shown; latch it
                # so sustained noise later in the session never re-fires.
                noise_monitor.mark_notice_shown()

    return jsonify({
        "status": "recorded",
        "session_id": session.id,
        "verdict": verdict,
        "confidence": confidence,
        "ml_mode": ml_mode,
        "gaze_label": gaze_label,
        "engagement_score": engagement_score,
        "face_detected": ml_features.get("face_detected") if ml_features else None,
        "noise_dbfs": data.noise_dbfs,
        "noise_baseline_dbfs": noise_monitor.baseline_dbfs if noise_monitor else None,
        "noise_triggered": noise_triggered,
        "intervention_triggered": intervention_data is not None,
        "intervention": intervention_data,
    }), 200


@session_bp.route("/<int:session_id>/trigger-intervention", methods=["POST"])
@jwt_required()
@role_required("student")
def trigger_intervention(session_id):
    """Manually force a tier intervention for demo / practice (student-owned active session)."""
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    session = db.session.get(LearningSession, session_id)
    if not session or session.student_id != student.id:
        return jsonify({"error": "Learning session not found"}), 404
    if session.end_time is not None:
        return jsonify({"error": "Cannot trigger intervention on an ended session"}), 400
    if not session.is_monitored:
        return jsonify({"error": "Session is not monitored"}), 400

    raw_data = request.get_json(silent=True) or {}
    try:
        data = TriggerInterventionSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    module = db.session.get(Module, session.module_id)
    subject_id = module.subject_id if module else None

    if session.id not in SESSION_ENGINES:
        SESSION_ENGINES[session.id] = (
            _build_engine(subject_id) if subject_id else InterventionEngine()
        )
    engine = SESSION_ENGINES[session.id]

    triggered = engine.force_intervention(
        tier=data.tier,
        is_quiz_context=bool(data.is_quiz_context),
    )
    if not triggered:
        return jsonify({
            "error": "Cannot trigger intervention while another is pending, or tier is disabled",
            "intervention_triggered": False,
            "intervention": None,
        }), 409

    now_dt = datetime.utcnow()
    intervention_data = _persist_triggered_intervention(session, triggered, None, now_dt)
    return jsonify({
        "intervention_triggered": True,
        "intervention": intervention_data,
    }), 200


@session_bp.route("/<int:session_id>/intervention-response", methods=["POST"])
@jwt_required()
@role_required("student")
def record_intervention_response(session_id):
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    session = db.session.get(LearningSession, session_id)
    if not session or session.student_id != student.id:
        return jsonify({"error": "Learning session not found"}), 404

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = InterventionResponseSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    log_entry = db.session.get(InterventionLog, data.intervention_id)
    if not log_entry or log_entry.session_id != session.id:
        return jsonify({"error": "Intervention log record not found for this session"}), 404

    now_dt = datetime.utcnow()
    log_entry.user_response = data.user_response
    if data.noise_action and log_entry.intervention_type == TYPE_NOISE_NOTICE:
        log_entry.noise_action = data.noise_action
    if log_entry.triggered_at:
        log_entry.reengaged_in_seconds = max(0.0, (now_dt - log_entry.triggered_at).total_seconds())

    mq = MilestoneQuestion.query.filter_by(intervention_id=log_entry.id).first()
    if mq and data.student_answer is not None:
        mq.student_answer = str(data.student_answer)
        is_correct = None
        if data.selected_option is not None:
            correct = mq.correct_option
            item_id = data.milestone_item_id or mq.milestone_item_id
            if item_id:
                item = db.session.get(ModuleMilestoneItem, item_id)
                if item:
                    correct = int(item.correct_option)
            if correct is not None:
                is_correct = int(data.selected_option) == int(correct)
        mq.is_correct = is_correct

    if session.id in SESSION_ENGINES:
        SESSION_ENGINES[session.id].record_outcome(data.user_response)

    db.session.commit()

    return jsonify({
        "message": "Intervention response recorded successfully",
        "intervention_id": log_entry.id,
        "user_response": log_entry.user_response,
        "noise_action": getattr(log_entry, "noise_action", None),
        "reengaged_in_seconds": log_entry.reengaged_in_seconds,
        "is_correct": mq.is_correct if mq else None,
    }), 200


@session_bp.route("/<int:session_id>/stop", methods=["POST"])
@jwt_required()
@role_required("student")
def stop_session(session_id):
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    session = db.session.get(LearningSession, session_id)
    if not session or session.student_id != student.id:
        return jsonify({"error": "Learning session not found"}), 404

    now_dt = datetime.utcnow()
    # Idempotent end: only the first successful UPDATE sets end_time.
    ended_rows = db.session.execute(
        update(LearningSession)
        .where(
            LearningSession.id == session.id,
            LearningSession.end_time.is_(None),
        )
        .values(end_time=now_dt)
    ).rowcount
    if ended_rows:
        open_ev = get_open_distraction_event(session.id)
        if open_ev:
            open_ev.ended_at = now_dt
    db.session.commit()
    db.session.refresh(session)

    if session.id in SESSION_ENGINES:
        del SESSION_ENGINES[session.id]
    SESSION_NOISE_MONITORS.pop(session.id, None)

    try:
        MLService().clear_session(session.id)
    except Exception:
        pass

    duration_seconds = 0
    if session.start_time and session.end_time:
        duration_seconds = int((session.end_time - session.start_time).total_seconds())

    total_events = DistractionEvent.query.filter_by(session_id=session.id).count()
    distraction_events = DistractionEvent.query.filter_by(
        session_id=session.id, verdict=DB_DISTRACTED
    ).count()
    focused_events = DistractionEvent.query.filter(
        DistractionEvent.session_id == session.id,
        DistractionEvent.ended_at.isnot(None),
    ).count()
    total_interventions = InterventionLog.query.filter_by(session_id=session.id).count()
    focus_percentage = compute_session_focus_percentage(session, now_dt=session.end_time)

    gamification = {}
    # Concurrent-safe: only the request that claims xp_awarded awards XP.
    should_award = claim_session_xp_award(session.id)
    if should_award:
        try:
            from app.services.gamification_service import award_session_xp
            gamification = award_session_xp(
                student.id,
                duration_seconds=duration_seconds,
                focus_percentage=focus_percentage,
            )
        except Exception:
            gamification = {}
    else:
        try:
            from app.services.gamification_service import get_progress_payload
            gamification = {
                "xp_gained": 0,
                "focus_minutes": 0,
                "progress": get_progress_payload(student.id),
                "new_badges": [],
            }
        except Exception:
            gamification = {"xp_gained": 0, "focus_minutes": 0}

    return jsonify({
        "message": "Learning session completed",
        "session_id": session.id,
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "duration_seconds": duration_seconds,
        "total_events": total_events,
        "focused_events": focused_events,
        "distraction_events": distraction_events,
        "focus_percentage": focus_percentage,
        "total_interventions": total_interventions,
        "xp_gained": gamification.get("xp_gained", 0),
        "focus_minutes": gamification.get("focus_minutes", 0),
        "progress": gamification.get("progress"),
        "new_badges": gamification.get("new_badges", []),
    }), 200
