"""
Socket.IO telemetry path — parity with REST heartbeat interventions.
"""
from datetime import datetime

from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import emit, join_room, disconnect

from app.extensions import db, socketio
from app.db_models import LearningSession, InterventionLog, Module, Student
from app.services.ml_service import MLService
from app.services.intervention_engine import InterventionEngine
from app.routes.session import (
    SESSION_ENGINES,
    _build_engine,
    upsert_distraction_episode,
    _persist_triggered_intervention,
)

active_engines = SESSION_ENGINES
# Maps Socket.IO sid → authenticated user id
_SID_USERS = {}


def _token_from_handshake(auth=None):
    token = None
    if isinstance(auth, dict):
        token = auth.get("token") or auth.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
    return token


def _user_id_from_token(token):
    if not token:
        return None
    try:
        decoded = decode_token(token)
        return int(decoded.get("sub"))
    except Exception:
        return None


def _current_user_id():
    return _SID_USERS.get(request.sid)


def _owns_session(session: LearningSession, user_id: int) -> bool:
    if not user_id or not session:
        return False
    student = Student.query.filter_by(user_id=user_id).first()
    return bool(student and session.student_id == student.id)


def _ensure_engine(session: LearningSession) -> InterventionEngine:
    if session.id in active_engines and isinstance(active_engines[session.id], InterventionEngine):
        return active_engines[session.id]
    module = db.session.get(Module, session.module_id)
    subject_id = module.subject_id if module else None
    engine = _build_engine(subject_id) if subject_id else InterventionEngine()
    active_engines[session.id] = engine
    return engine


def init_telemetry_events():
    @socketio.on("connect")
    def handle_connect(auth=None):
        user_id = _user_id_from_token(_token_from_handshake(auth))
        if user_id is None:
            emit("connection_error", {"error": "Unauthorized"})
            disconnect()
            return False
        _SID_USERS[request.sid] = user_id
        emit("connection_ack", {"status": "connected", "user_id": user_id})

    @socketio.on("disconnect")
    def handle_disconnect():
        _SID_USERS.pop(request.sid, None)

    @socketio.on("join_session")
    def handle_join_session(data):
        data = data or {}
        session_id = data.get("session_id")
        if not session_id:
            return
        user_id = _current_user_id()
        session = db.session.get(LearningSession, int(session_id))
        if not session or session.end_time is not None:
            emit("session_error", {"error": "Session not found or already ended"})
            return
        if not _owns_session(session, user_id):
            emit("session_error", {"error": "Forbidden: not your session"})
            return

        join_room(str(session.id))
        _ensure_engine(session)
        emit("session_joined", {"session_id": session.id})

    @socketio.on("telemetry_window")
    def handle_telemetry_window(data):
        data = data or {}
        session_id = data.get("session_id")
        if not session_id:
            return
        session_id = int(session_id)
        user_id = _current_user_id()
        session = db.session.get(LearningSession, session_id)
        if not session or session.end_time is not None:
            return
        if not _owns_session(session, user_id):
            emit("session_error", {"error": "Forbidden: not your session"})
            return

        features = data.get("features", {}) or {}
        is_quiz_context = bool(data.get("is_quiz_context", False))
        now_dt = datetime.utcnow()
        ml_service = MLService()

        if data.get("image"):
            verdict, confidence, _feats = ml_service.predict_frame_image(
                data["image"], session_id=session_id
            )
        elif features:
            verdict, confidence = ml_service.predict_window_features(features)
        else:
            emit("session_error", {"error": "image or features required"})
            return

        episode, just_closed = upsert_distraction_episode(
            session_id, verdict, confidence, now_dt
        )

        engine = _ensure_engine(session)
        is_distracted = verdict == "DISTRACTED"
        open_episode = episode if is_distracted and not just_closed else None

        intervention = engine.decide_intervention(
            distraction_event=open_episode,
            is_distracted=is_distracted,
            is_quiz_context=is_quiz_context,
            wall_now=now_dt,
        )

        emit(
            "telemetry_verdict",
            {"verdict": verdict, "confidence": confidence, "session_id": session_id},
            room=str(session_id),
        )

        if intervention and session.is_monitored:
            data_out = _persist_triggered_intervention(
                session,
                intervention,
                open_episode.id if open_episode else None,
                now_dt,
            )
            emit(
                "intervention_triggered",
                {
                    **data_out,
                    "type": data_out["intervention_type"],
                },
                room=str(session_id),
            )

    @socketio.on("intervention_outcome")
    def handle_intervention_outcome(data):
        data = data or {}
        session_id = data.get("session_id")
        intervention_id = data.get("intervention_id")
        outcome = (data.get("outcome") or data.get("user_response") or "").lower()
        if not session_id or not intervention_id:
            return
        session_id = int(session_id)
        user_id = _current_user_id()
        session = db.session.get(LearningSession, session_id)
        if not session or not _owns_session(session, user_id):
            emit("intervention_error", {"error": "Forbidden: not your session"})
            return
        log_entry = db.session.get(InterventionLog, int(intervention_id))
        if not log_entry or log_entry.session_id != session_id:
            emit("intervention_error", {"error": "Intervention not found"})
            return
        if outcome not in {"reengaged", "ignored", "ended"}:
            emit("intervention_error", {"error": "Invalid outcome"})
            return

        now_dt = datetime.utcnow()
        log_entry.user_response = outcome
        if log_entry.triggered_at:
            log_entry.reengaged_in_seconds = max(
                0.0, (now_dt - log_entry.triggered_at).total_seconds()
            )
        if session_id in active_engines and isinstance(
            active_engines[session_id], InterventionEngine
        ):
            active_engines[session_id].record_outcome(outcome)
        db.session.commit()
        emit(
            "intervention_outcome_ack",
            {"intervention_id": log_entry.id, "user_response": outcome},
            room=str(session_id),
        )
