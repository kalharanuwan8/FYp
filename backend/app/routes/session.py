from datetime import datetime, timedelta

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
    MonitoringObservation,
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
from app.services.focus_metrics import (
    apply_coverage_to_session,
    compute_session_coverage,
)
from app.services.observation_coverage import EPISODE_GAP_MAX, FOCUS_METRIC_VERSION, T_SUPPORT
from app.utils.decorators import role_required

session_bp = Blueprint("session", __name__)

# In-memory registry of active session intervention engines keyed by session_id
SESSION_ENGINES = {}
# 6 frames x 200 KB base64 + JSON overhead; well above a real 2 fps heartbeat (~60 KB).
MAX_HEARTBEAT_BYTES = 2 * 1024 * 1024

# Per-session background-noise monitors keyed by session_id
SESSION_NOISE_MONITORS = {}

# Postgres enum monitoring_verdict is lowercase; API/ML stay UPPERCASE.
DB_DISTRACTED = "distracted"
DB_FOCUSED = "focused"
API_UNKNOWN = "UNKNOWN"
API_FOCUSED = "FOCUSED"
API_DISTRACTED = "DISTRACTED"

# PLAN 4: brief UNKNOWN runs pause the episode clock but do not close it.
UNKNOWN_HOLD_SEC = 5.0


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


def claim_session_xp_award(session_id: int, *, commit: bool = True) -> bool:
    """
    Atomically claim the one-time session XP award.

    Returns True only for the caller that flipped xp_awarded from False→True.
    Safe under concurrent stop requests (UPDATE ... WHERE xp_awarded = false).

    When commit=False, the UPDATE stays in the current transaction so XP reward
    updates can share the same commit/rollback (Phase 2A).
    """
    result = db.session.execute(
        update(LearningSession)
        .where(
            LearningSession.id == session_id,
            LearningSession.xp_awarded.is_(False),
        )
        .values(xp_awarded=True)
    )
    if commit:
        db.session.commit()
    return int(result.rowcount or 0) == 1


def award_claimed_session_xp(
    *,
    session_id: int,
    student_id: int,
    observed_focused_seconds: float,
    max_retries: int = 1,
) -> dict:
    """
    Claim xp_awarded and apply reward updates in one DB transaction.
    On reward failure, roll back the claim so a later stop can retry.
    """
    from app.services.gamification_service import award_session_xp, get_progress_payload

    empty = {
        "xp_gained": 0,
        "focus_minutes": 0,
        "progress": None,
        "new_badges": [],
    }
    attempt = 0
    while attempt <= max_retries:
        attempt += 1
        try:
            claimed = claim_session_xp_award(session_id, commit=False)
            if not claimed:
                db.session.rollback()
                try:
                    empty["progress"] = get_progress_payload(student_id)
                except Exception:
                    pass
                return empty
            gamification = award_session_xp(
                student_id,
                observed_focused_seconds=observed_focused_seconds,
                commit=False,
            )
            db.session.commit()
            return gamification
        except Exception:
            db.session.rollback()
            if attempt > max_retries:
                try:
                    empty["progress"] = get_progress_payload(student_id)
                except Exception:
                    pass
                return empty
    return empty


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


def _prior_observation(session_id: int, before_dt: datetime):
    """Most recent MonitoringObservation strictly before ``before_dt``."""
    return (
        MonitoringObservation.query.filter_by(session_id=session_id)
        .filter(MonitoringObservation.observed_at < before_dt)
        .order_by(MonitoringObservation.observed_at.desc())
        .first()
    )


def _last_distracted_observation_at(session_id: int, now_dt: datetime):
    """Most recent DISTRACTED observation at-or-before now (for UNKNOWN hold)."""
    return (
        MonitoringObservation.query.filter(
            MonitoringObservation.session_id == session_id,
            MonitoringObservation.observed_at <= now_dt,
            MonitoringObservation.state == API_DISTRACTED,
        )
        .order_by(MonitoringObservation.observed_at.desc())
        .first()
    )


def upsert_distraction_episode(session_id: int, verdict: str, confidence: float, now_dt: datetime):
    """
    Open-episode semantics:
      DISTRACTED + no open → create
      DISTRACTED + open, gap ≤ EPISODE_GAP_MAX from prior valid DISTRACTED → keep open
      DISTRACTED + open, gap > EPISODE_GAP_MAX → close at prior+T_SUPPORT, open new
        (unknown gap must not accumulate toward visual escalation)
      FOCUSED + open → close with ended_at (re-engagement)
      UNKNOWN + open, ≤ UNKNOWN_HOLD_SEC since last DISTRACTED → keep open (paused)
      UNKNOWN + open, longer → close at UNKNOWN time (interrupted; not re-engagement)
      UNKNOWN + no open → no-op
    Returns (open_or_closed_event, just_closed: bool)

    `verdict` is the API/ML uppercase value; DB rows use lowercase enum values.
    """
    open_event = get_open_distraction_event(session_id)
    verdict_u = (verdict or "").upper().strip()

    if verdict_u == API_DISTRACTED:
        if open_event:
            prior = _prior_observation(session_id, now_dt)
            prior_at = None
            if prior is not None and (prior.state or "").upper() == API_DISTRACTED:
                prior_at = prior.observed_at
            elif open_event.started_at is not None:
                prior_at = open_event.started_at
            if prior_at is not None:
                gap = (now_dt - prior_at).total_seconds()
                if gap > EPISODE_GAP_MAX:
                    # Break continuity across the unknown remainder after support.
                    open_event.ended_at = prior_at + timedelta(seconds=T_SUPPORT)
                    db.session.commit()
                    event = DistractionEvent(
                        session_id=session_id,
                        verdict=DB_DISTRACTED,
                        confidence=confidence if confidence is not None else 0.0,
                        started_at=now_dt,
                    )
                    db.session.add(event)
                    db.session.commit()
                    return event, False
            open_event.confidence = (
                confidence if confidence is not None else open_event.confidence
            )
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

    if verdict_u == API_UNKNOWN:
        if open_event:
            last_dist = _last_distracted_observation_at(session_id, now_dt)
            anchor = last_dist.observed_at if last_dist is not None else open_event.started_at
            hold_for = (now_dt - anchor).total_seconds() if anchor is not None else 0.0
            if hold_for <= UNKNOWN_HOLD_SEC:
                # Brief UNKNOWN: keep episode open but do not advance the clock
                # (intervention path gets episode_clock_held / UNKNOWN hold).
                return open_event, False
            open_event.ended_at = now_dt
            db.session.commit()
            return open_event, True
        return None, False

    if verdict_u == API_FOCUSED and open_event:
        open_event.ended_at = now_dt
        db.session.commit()
        return open_event, True
    return None, False


def record_monitoring_observation(
    session_id: int,
    *,
    state: str,
    now_dt: datetime,
    confidence,
    face_detected,
    ml_mode,
    reason,
) -> MonitoringObservation:
    """Persist one heartbeat observation for coverage accounting."""
    state_u = (state or API_UNKNOWN).upper().strip()
    conf = None
    if state_u in (API_FOCUSED, API_DISTRACTED) and confidence is not None:
        conf = float(confidence)
    face = face_detected if state_u != API_UNKNOWN else (
        face_detected if face_detected is False else None
    )
    row = MonitoringObservation(
        session_id=session_id,
        observed_at=now_dt,
        state=state_u,
        confidence=conf,
        face_detected=face,
        ml_mode=ml_mode,
        reason=reason,
    )
    db.session.add(row)
    db.session.commit()
    return row


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

    # Align engine pending id with the DB log id the client will echo back.
    pending = getattr(triggered, "intervention_id", None)
    eng_pending = getattr(
        SESSION_ENGINES.get(session.id), "_pending", None
    ) if session.id in SESSION_ENGINES else None
    if eng_pending is not None and (
        pending is None or eng_pending.id == pending
    ):
        eng_pending.id = str(log_entry.id)

    return {
        "intervention_id": log_entry.id,
        "tier": triggered.tier,
        "intervention_type": triggered.intervention_type,
        "message": triggered.message,
        "triggered_at": now_dt.isoformat(),
        "payload": payload,
        "source": getattr(triggered, "source", None),
        "deadline": getattr(triggered, "deadline", None),
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
    ml_service = MLService()
    for s in active_sessions:
        s.end_time = now_dt
        open_ev = get_open_distraction_event(s.id)
        if open_ev:
            open_ev.ended_at = now_dt
        if s.id in SESSION_ENGINES:
            del SESSION_ENGINES[s.id]
        SESSION_NOISE_MONITORS.pop(s.id, None)
        # Release per-session MediaPipe landmarker when auto-closing prior session
        ml_service.clear_session(s.id)

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

    if (request.content_length or 0) > MAX_HEARTBEAT_BYTES:
        return jsonify({"error": "Heartbeat payload too large"}), 413

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

    is_testing = bool(current_app.config.get("TESTING"))

    if not session.is_monitored:
        # No camera inference without a monitored (consented) session.
        verdict, confidence = API_UNKNOWN, None
        ml_features = {"reason": "not_monitored"}
        ml_mode = ml_service.ml_mode
    elif data.frames or data.image:
        if hasattr(ml_service, "set_session_calibrating"):
            ml_service.set_session_calibrating(session.id, bool(data.calibrating))
        if data.frames:
            ml_verdict, ml_conf, ml_features = ml_service.predict_frames(
                [(f.t_ms / 1000.0, f.image) for f in data.frames], session_id=session.id
            )
        else:
            ml_verdict, ml_conf, ml_features = ml_service.predict_frame_image(
                data.image, session_id=session.id
            )
        verdict = ml_verdict
        confidence = ml_conf
        gaze_label = ml_features.get("gaze_label", gaze_label)
        engagement_score = ml_features.get("engagement_score", engagement_score)
        ml_mode = ml_features.get("ml_mode") or ml_service.ml_mode
    elif (data.hidden_ms or 0) >= 3000 or (data.blurred_ms or 0) >= 5000:
        # Lightweight heartbeat while the tab is hidden / window blurred (no frames).
        verdict, confidence = API_UNKNOWN, None
        ml_features = {"reason": "browser_signal_only"}
        ml_mode = ml_service.ml_mode
    elif data.features and is_testing:
        verdict, confidence = ml_service.predict_window_features(data.features)
        ml_features = {"face_detected": data.features.get("face_detected")}
        ml_mode = ml_service.ml_mode
    elif data.features:
        # A client must not be able to report its own focus state.
        return jsonify({"error": "Precomputed features are not accepted; send webcam frames"}), 400
    elif is_testing and data.verdict:
        # Unit tests exercise the intervention engine without ML frames
        verdict = data.verdict
        confidence = data.confidence if data.confidence is not None else (
            None if data.verdict == API_UNKNOWN else 1.0
        )
        ml_features = {"reason": "test_injected"}
    else:
        return jsonify({
            "error": "Webcam frames (frames or image) required for heartbeat telemetry"
        }), 400

    # Browser signals override camera (PLAN 4): tab hidden ≥3 s / blur ≥5 s.
    browser_source = None
    if session.is_monitored:
        if (data.hidden_ms or 0) >= 3000:
            verdict, confidence = API_DISTRACTED, 1.0
            browser_source = "tab"
            ml_features = {**(ml_features or {}), "reason": "tab_hidden", "source": "tab"}
        elif (data.blurred_ms or 0) >= 5000:
            verdict, confidence = API_DISTRACTED, 1.0
            browser_source = "blur"
            ml_features = {**(ml_features or {}), "reason": "window_blur", "source": "blur"}

    if engagement_score is None and confidence is not None and verdict == API_DISTRACTED:
        engagement_score = round(1.0 - float(confidence), 4)
    elif engagement_score is None and confidence is not None and verdict == API_FOCUSED:
        engagement_score = round(float(confidence), 4)

    record_monitoring_observation(
        session.id,
        state=verdict,
        now_dt=now_dt,
        confidence=confidence,
        face_detected=ml_features.get("face_detected") if ml_features else None,
        ml_mode=ml_mode,
        reason=(ml_features or {}).get("reason"),
    )

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
        # Expire unanswered prompts (20 s) before deciding the next one.
        if hasattr(engine, "tick"):
            engine.tick()
        # Pass observation_state explicitly so UNKNOWN does not invoke focus-reset.
        is_distracted = verdict == API_DISTRACTED
        open_episode = episode if is_distracted and not just_closed else None
        content_state = (data.content_state or "none").lower()
        # Hold episode clock while lesson video is deliberately paused / ended,
        # or while a prompt/break is still open.
        episode_held = content_state in {"paused", "ended"}
        if getattr(engine, "_pending", None) is not None:
            episode_held = True
        src = browser_source or (ml_features or {}).get("source") or "model6"

        # When UNKNOWN briefly keeps the episode open, still pass the open
        # event so the engine can hold without re-firing cues.
        if (
            verdict == API_UNKNOWN
            and episode is not None
            and not just_closed
            and open_episode is None
        ):
            open_episode = episode

        triggered = engine.decide_intervention(
            distraction_event=open_episode,
            is_distracted=is_distracted,
            is_quiz_context=bool(data.is_quiz_context),
            wall_now=now_dt,
            observation_state=verdict,
            source=src,
            episode_clock_held=episode_held,
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

    face_out = ml_features.get("face_detected") if ml_features else None
    reason_out = (ml_features or {}).get("reason")
    if verdict == API_UNKNOWN:
        # Keep face_detected during calibration so the UI can retry if no face.
        # no_face keeps face_detected=false; other UNKNOWN reasons stay null.
        if reason_out != "calibrating" and face_out is not False:
            face_out = None
        gaze_label = None
        engagement_score = None
        confidence = None

    # Additive diagnostics for thesis/debug; existing keys keep their meaning.
    diagnostics = {
        "inference_path": (ml_features or {}).get("inference_path"),
        "gaze_label": (ml_features or {}).get("gaze_label", gaze_label),
        "head_pose_yaw": (ml_features or {}).get("head_pose_yaw"),
        "head_pose_pitch": (ml_features or {}).get("head_pose_pitch"),
        "head_pose_roll": (ml_features or {}).get("head_pose_roll"),
        "distract_prob": (ml_features or {}).get("distract_prob"),
        "face_box_px": (ml_features or {}).get("face_box_px"),
        "pose_baseline_yaw": (ml_features or {}).get("pose_baseline_yaw"),
        "pose_baseline_pitch": (ml_features or {}).get("pose_baseline_pitch"),
        "fusion_threshold": (ml_features or {}).get("fusion_threshold"),
    }

    return jsonify({
        "status": "recorded",
        "session_id": session.id,
        "verdict": verdict,
        "confidence": confidence,
        "ml_mode": ml_mode,
        "reason": reason_out,
        "gaze_label": gaze_label,
        "engagement_score": engagement_score,
        "face_detected": face_out,
        "diagnostics": diagnostics,
        "noise_dbfs": data.noise_dbfs,
        "noise_baseline_dbfs": noise_monitor.baseline_dbfs if noise_monitor else None,
        "noise_triggered": noise_triggered,
        "intervention_triggered": intervention_data is not None,
        "intervention": intervention_data,
        "focus_metric_version": FOCUS_METRIC_VERSION,
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
    if session.ended_at is not None:
        return jsonify({"error": "Session already ended"}), 409

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
    if data.self_report:
        log_entry.self_report = str(data.self_report)[:2000]
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

    return jsonify(_finalize_session(session, student.id)), 200


def _active_session_payload(session: LearningSession) -> dict:
    module = session.module
    subject = getattr(module, "subject", None) if module else None
    started = session.start_time
    return {
        "session_id": session.id,
        "module_id": session.module_id,
        "module_title": module.title if module else None,
        "subject_id": subject.id if subject else None,
        "subject_title": subject.title if subject else None,
        "start_time": started.isoformat() if started else None,
        "running_seconds": int((datetime.utcnow() - started).total_seconds()) if started else 0,
        "is_monitored": session.is_monitored,
    }


@session_bp.route("/active", methods=["GET"])
@jwt_required()
@role_required("student")
def list_active_sessions():
    """Open (not yet stopped) sessions for the current student, newest first."""
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    sessions = (
        LearningSession.query.filter_by(student_id=student.id, end_time=None)
        .order_by(LearningSession.start_time.desc())
        .all()
    )
    return jsonify({
        "count": len(sessions),
        "sessions": [_active_session_payload(s) for s in sessions],
    }), 200


@session_bp.route("/stop-active", methods=["POST"])
@jwt_required()
@role_required("student")
def stop_active_sessions():
    """
    Stop every open session for the current student — e.g. monitoring left
    running after a closed tab. Each session is finalized exactly like /stop.
    """
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    sessions = LearningSession.query.filter_by(student_id=student.id, end_time=None).all()
    summaries = [_finalize_session(s, student.id) for s in sessions]
    return jsonify({
        "message": f"Stopped {len(summaries)} monitoring session(s)",
        "stopped_count": len(summaries),
        "sessions": summaries,
    }), 200


def _finalize_session(session: LearningSession, student_id: int) -> dict:
    """End a session (idempotent), release runtime state, seal coverage and award XP."""
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

    coverage = compute_session_coverage(session, now_dt=session.end_time)
    apply_coverage_to_session(session, coverage)
    db.session.commit()
    db.session.refresh(session)

    # Concurrent-safe claim + reward in one transaction (Phase 2A).
    # Historical ended sessions sealed with xp_awarded=True at migration time.
    gamification = award_claimed_session_xp(
        session_id=session.id,
        student_id=student_id,
        observed_focused_seconds=coverage.observed_focused_seconds,
    )

    return {
        "message": "Learning session completed",
        "session_id": session.id,
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "duration_seconds": duration_seconds,
        "total_events": total_events,
        "focused_events": focused_events,
        "distraction_events": distraction_events,
        "focus_percentage": coverage.focus_percentage,
        "focus_metric_version": FOCUS_METRIC_VERSION,
        "observed_focused_seconds": round(coverage.observed_focused_seconds, 3),
        "observed_distracted_seconds": round(coverage.observed_distracted_seconds, 3),
        "unknown_seconds": round(coverage.unknown_seconds, 3),
        "monitoring_coverage_pct": round(coverage.monitoring_coverage_pct, 1),
        "total_interventions": total_interventions,
        "xp_gained": gamification.get("xp_gained", 0),
        "focus_minutes": gamification.get("focus_minutes", 0),
        "progress": gamification.get("progress"),
        "new_badges": gamification.get("new_badges", []),
    }
