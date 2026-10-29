"""Record-only behavioural events (idle on quiz / document)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.db_models import BehaviourEvent, ModuleContent, QuizAttempt, Student
from app.extensions import db
from app.services.dsm_indicators import IDLE_MIN_SECONDS
from app.utils.decorators import role_required

behaviour_bp = Blueprint("behaviour", __name__)


class IdleEventSchema(BaseModel):
    context: str
    duration_seconds: float = Field(..., ge=IDLE_MIN_SECONDS)
    started_at: Optional[str] = None
    quiz_attempt_id: Optional[int] = None
    module_content_id: Optional[int] = None

    @field_validator("context")
    @classmethod
    def validate_context(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ("quiz", "document"):
            raise ValueError("context must be quiz or document")
        return v


@behaviour_bp.route("/idle", methods=["POST"])
@jwt_required()
@role_required("student")
def record_idle():
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Missing JSON request body"}), 400
    try:
        data = IdleEventSchema.model_validate(raw)
    except ValidationError as err:
        details = [
            {"field": "->".join(str(x) for x in e["loc"]), "message": e["msg"]}
            for e in err.errors()
        ]
        return jsonify({"error": "Validation failed", "details": details}), 400

    if data.context == "quiz":
        if not data.quiz_attempt_id:
            return jsonify({"error": "quiz_attempt_id required for quiz context"}), 400
        attempt = db.session.get(QuizAttempt, data.quiz_attempt_id)
        if not attempt or attempt.student_id != student.id:
            return jsonify({"error": "Forbidden: quiz attempt not owned"}), 403
    elif data.context == "document":
        if not data.module_content_id:
            return jsonify({"error": "module_content_id required for document context"}), 400
        content = db.session.get(ModuleContent, data.module_content_id)
        if not content:
            return jsonify({"error": "Module content not found"}), 404

    started = datetime.utcnow()
    if data.started_at:
        try:
            started = datetime.fromisoformat(data.started_at.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
        except ValueError:
            return jsonify({"error": "Invalid started_at ISO timestamp"}), 400

    event = BehaviourEvent(
        student_id=student.id,
        indicator="idle",
        context=data.context,
        quiz_attempt_id=data.quiz_attempt_id,
        module_content_id=data.module_content_id,
        started_at=started,
        duration_seconds=float(data.duration_seconds),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify(event.to_dict()), 201
