from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import BaseModel, Field, EmailStr, ValidationError
from typing import Optional, Any, Dict

from app.db_models import User, Student, GuardianConsent, GradeLevel
from app.utils.decorators import role_required
from app.extensions import db
from app.services.gamification_service import get_progress_payload, list_student_badges

student_profile_bp = Blueprint("student_profile", __name__)


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
    }


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
