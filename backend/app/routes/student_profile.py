from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import BaseModel, Field, EmailStr, ValidationError, field_validator
from typing import Optional, Any, Dict, List

from app.db_models import User, Student, GuardianConsent, GradeLevel
from app.utils.decorators import role_required
from app.extensions import db
from app.services.gamification_service import get_progress_payload, list_student_badges
from app.schemas.session_schema import (
    FrameIn,
    ScreenInfo,
    CALIBRATION_PHASES,
    MAX_FRAMES_PER_HEARTBEAT,
)
from app.services.ml_service import MLService

student_profile_bp = Blueprint("student_profile", __name__)

# Same ballpark as a monitored heartbeat (frames are JPEG base64).
MAX_CALIB_BYTES = 2_500_000


class StudentProfileUpdateSchema(BaseModel):
    grade_level: Optional[str] = Field(None, min_length=1)
    guardian_name: Optional[str] = Field(None, min_length=1)
    guardian_email: Optional[EmailStr] = None
    # Accepted for backwards-compatible clients but ignored: only admins may
    # change GuardianConsent.consent_given (see auth.update_student_consent).
    consent_given: Optional[bool] = None
    student_assent: Optional[bool] = None
    onboarding_completed: Optional[bool] = None
    ui_preferences: Optional[Dict[str, Any]] = None
    daily_goal_minutes: Optional[int] = Field(None, ge=5, le=120)


class GazeCalibrationSchema(BaseModel):
    """Calibration-only batch — same frame shape as a heartbeat, no learning session."""

    frames: Optional[List[FrameIn]] = Field(None, max_length=MAX_FRAMES_PER_HEARTBEAT)
    screen: Optional[ScreenInfo] = None
    calibration_phase: Optional[str] = None
    calibrating: Optional[bool] = False

    @field_validator("calibration_phase")
    @classmethod
    def validate_calibration_phase(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_lower = v.lower().strip()
        if v_lower not in CALIBRATION_PHASES:
            raise ValueError(f"calibration_phase must be one of {list(CALIBRATION_PHASES)}")
        return v_lower


def _gaze_calibrated(student) -> bool:
    payload = getattr(student, "gaze_calibration", None)
    if isinstance(payload, str):
        import json

        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return False
    if not isinstance(payload, dict):
        return False
    mapper = payload.get("mapper") if isinstance(payload.get("mapper"), dict) else payload
    return bool(mapper and mapper.get("ok") and mapper.get("cx") and mapper.get("cy"))


def _profile_payload(user, student):
    consent = student.guardian_consent
    guardian_name = consent.guardian_name if consent else None
    guardian_email = consent.guardian_email if consent else None
    consent_given = consent.consent_given if consent else False

    # Guardian consent is recorded by teacher/admin; student onboarding needs
    # grade + assent (+ optional theme prefs). Legacy: treat old consent path as complete.
    onboarding_done = bool(
        student.onboarding_completed
        or (
            student.grade_level
            and student.student_assent
        )
        or (
            student.grade_level
            and consent
            and consent_given
            and guardian_name
            and guardian_email
        )
    )

    return {
        "id": student.id,
        "user_id": student.user_id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "grade_level": student.grade_level,
        "guardian_name": guardian_name,
        "guardian_email": guardian_email,
        "consent_given": consent_given,
        "student_assent": bool(student.student_assent),
        "pseudonym_id": student.pseudonym_id,
        "ui_preferences": student.ui_preferences or {},
        "onboarding_completed": onboarding_done,
        "gaze_calibrated": _gaze_calibrated(student),
    }


def persist_student_gaze_calibration(student, scorer, screen=None) -> Optional[dict]:
    """Write the scorer's fit onto the student row. Returns the saved payload or None."""
    if student is None or scorer is None or not hasattr(scorer, "export_calibration"):
        return None
    exported = scorer.export_calibration()
    if not exported:
        return None
    if screen and not exported.get("screen"):
        exported["screen"] = screen
    exported["calibrated_at"] = datetime.utcnow().isoformat() + "Z"
    # Re-assign a fresh dict so SQLAlchemy always marks the JSON column dirty.
    student.gaze_calibration = dict(exported)
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(student, "gaze_calibration")
    db.session.add(student)
    db.session.commit()
    return dict(exported)


@student_profile_bp.route("/profile", methods=["GET"])
@jwt_required()
@role_required("student")
def get_student_profile():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user or not user.student_profile:
        return jsonify({"error": "Student profile not found"}), 404

    return jsonify(_profile_payload(user, user.student_profile)), 200


@student_profile_bp.route("/profile", methods=["PATCH"])
@jwt_required()
@role_required("student")
def update_student_profile():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user or not user.student_profile:
        return jsonify({"error": "Student profile not found"}), 404

    student = user.student_profile
    raw_data = request.get_json(silent=True) or {}

    try:
        data = StudentProfileUpdateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": err.errors()}), 400

    if data.grade_level is not None:
        grade_name = data.grade_level.strip()
        if grade_name:
            gl = GradeLevel.query.filter_by(name=grade_name).first()
            if not gl:
                gl_ci = GradeLevel.query.filter(GradeLevel.name.ilike(grade_name)).first()
                if gl_ci:
                    grade_name = gl_ci.name
            student.grade_level = grade_name

    if data.ui_preferences is not None:
        existing = dict(student.ui_preferences or {})
        existing.update(data.ui_preferences)
        student.ui_preferences = existing

    if data.student_assent is not None:
        student.student_assent = data.student_assent

    if data.onboarding_completed is not None:
        student.onboarding_completed = data.onboarding_completed

    if data.daily_goal_minutes is not None:
        from app.services.gamification_service import get_or_create_progress
        progress = get_or_create_progress(student.id)
        progress.daily_goal_minutes = data.daily_goal_minutes

    # Guardian contact fields may be updated by the student for display, but
    # consent_given is admin-only and is never written here.
    consent = student.guardian_consent
    if data.guardian_name is not None or data.guardian_email is not None:
        if not consent:
            consent = GuardianConsent(
                student_id=student.id,
                guardian_name=(
                    data.guardian_name.strip() if data.guardian_name else "Parent/Guardian"
                ),
                guardian_email=(
                    str(data.guardian_email) if data.guardian_email else "guardian@example.com"
                ),
                consent_given=False,
            )
            db.session.add(consent)
            db.session.flush()

        if data.guardian_name is not None:
            consent.guardian_name = data.guardian_name.strip()
        if data.guardian_email is not None:
            consent.guardian_email = str(data.guardian_email)

    # Auto-complete onboarding when grade + assent present
    if student.grade_level and student.student_assent:
        student.onboarding_completed = True

    db.session.commit()
    return jsonify({
        "message": "Student profile updated successfully",
        **_profile_payload(user, student),
    }), 200


@student_profile_bp.route("/gaze-calibration", methods=["POST"])
@jwt_required()
@role_required("student")
def post_gaze_calibration():
    """Run screen-gaze calibration without opening a learning session."""
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user or not user.student_profile:
        return jsonify({"error": "Student profile not found"}), 404

    student = user.student_profile
    if (request.content_length or 0) > MAX_CALIB_BYTES:
        return jsonify({"error": "Calibration payload too large"}), 413

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = GazeCalibrationSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": err.errors()}), 400

    if not data.frames and data.calibration_phase not in ("start", "finish"):
        return jsonify({"error": "frames or calibration_phase required"}), 400

    ml_service = MLService()
    frame_args = []
    for f in data.frames or []:
        if f.calib_target is not None:
            frame_args.append(
                (
                    f.t_ms / 1000.0,
                    f.image,
                    {"x": f.calib_target.x, "y": f.calib_target.y},
                )
            )
        else:
            frame_args.append((f.t_ms / 1000.0, f.image))

    extra = {}
    if data.calibration_phase:
        extra["calibration_phase"] = data.calibration_phase
    if data.screen is not None:
        extra["screen"] = data.screen.model_dump()

    scorer_key = f"student_calib_{student.id}"
    _, _, ml_features = ml_service.predict_frames(
        frame_args, session_id=scorer_key, **extra
    )
    calibration = (ml_features or {}).get("calibration") or {}

    saved = False
    if data.calibration_phase == "finish" and calibration.get("ok"):
        scorer, _lock = ml_service._live_scorer_for(scorer_key)
        screen = data.screen.model_dump() if data.screen is not None else None
        if persist_student_gaze_calibration(student, scorer, screen=screen):
            saved = True
        ml_service.clear_session(scorer_key)
    elif data.calibration_phase == "finish":
        # Failed fit — drop the temporary scorer so the next attempt starts clean.
        ml_service.clear_session(scorer_key)

    face_detected = ml_features.get("face_detected") if ml_features else None
    return jsonify(
        {
            "calibration": calibration,
            "saved": saved,
            "gaze_calibrated": _gaze_calibrated(student),
            "face_detected": face_detected,
            "reason": (ml_features or {}).get("reason"),
        }
    ), 200


@student_profile_bp.route("/progress", methods=["GET"])
@jwt_required()
@role_required("student")
def get_student_progress():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user or not user.student_profile:
        return jsonify({"error": "Student profile not found"}), 404
    return jsonify(get_progress_payload(user.student_profile.id)), 200


@student_profile_bp.route("/badges", methods=["GET"])
@jwt_required()
@role_required("student")
def get_student_badges():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user or not user.student_profile:
        return jsonify({"error": "Student profile not found"}), 404
    return jsonify({"badges": list_student_badges(user.student_profile.id)}), 200
