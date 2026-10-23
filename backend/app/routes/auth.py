import bcrypt
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from pydantic import ValidationError

from app.db_models import User, Student, Teacher, GuardianConsent
from app.schemas.auth_schema import LoginSchema, RegisterSchema
from app.services.user_service import create_user_from_data
from app.utils.decorators import role_required
from app.extensions import db

auth_bp = Blueprint("auth", __name__)

def format_validation_errors(err: ValidationError):
    details = []
    for e in err.errors():
        field = "->".join(str(x) for x in e["loc"]) if e["loc"] else "body"
        details.append({"field": field, "message": e["msg"]})
    return details

@auth_bp.route("/login", methods=["POST"])
def login():
    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = LoginSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    user = User.query.filter_by(email=data.email).first()
    if not user or not user.is_active:
        return jsonify({"error": "Invalid email or password"}), 401

    # Compare password using bcrypt.checkpw
    if not bcrypt.checkpw(data.password.encode("utf-8"), user.password.encode("utf-8")):
        return jsonify({"error": "Invalid email or password"}), 401

    # Create JWT access token
    role_str = str(user.role).lower()
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": role_str}
    )

    # Update last_login_at
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "access_token": access_token,
        "user": {
            "id": user.id,
            "role": role_str,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email
        }
    }), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        return jsonify({"error": "User profile not found or inactive"}), 401
    return jsonify({
        "user": user.to_dict()
    }), 200


@auth_bp.route("/register", methods=["POST"])
@jwt_required()
@role_required("admin")
def register():
    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = RegisterSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    # Check if email is already taken
    existing_user = User.query.filter_by(email=data.email).first()
    if existing_user:
        return jsonify({"error": "A user with this email already exists"}), 400

    admin_id = get_jwt_identity()
    created_by_id = int(admin_id) if str(admin_id).isdigit() else None

    try:
        new_user = create_user_from_data(data, created_by_id=created_by_id)
        db.session.commit()

        return jsonify({
            "message": "User registered successfully",
            "user": new_user.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Registration failed: {e}")
        return jsonify({"error": "Registration failed. Please try again."}), 500


def _can_access_student_consent(student: Student) -> bool:
    """Admin, or the student themselves. Teachers cannot read arbitrary consent."""
    claims = get_jwt()
    role = str(claims.get("role") or "").lower()
    user_id = int(get_jwt_identity())
    if role == "admin":
        return True
    if role == "student" and student.user_id == user_id:
        return True
    return False


@auth_bp.route("/students/<int:student_id>/consent", methods=["GET"])
@jwt_required()
def get_student_consent(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    if not _can_access_student_consent(student):
        return jsonify({"error": "Forbidden: cannot view this student's consent"}), 403

    consent = GuardianConsent.query.filter_by(student_id=student.id).first()
    if not consent:
        return jsonify({"consent_given": False, "student_id": student.id}), 200

    return jsonify({
        "student_id": student.id,
        "guardian_name": consent.guardian_name,
        "guardian_email": consent.guardian_email,
        "consent_given": consent.consent_given,
        "consent_timestamp": consent.consented_at.isoformat() if consent.consented_at else None
    }), 200


@auth_bp.route("/students/<int:student_id>/consent", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_student_consent(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    raw_data = request.get_json(silent=True) or {}
    consent_given = raw_data.get("consent_given", True)

    consent = GuardianConsent.query.filter_by(student_id=student.id).first()
    if not consent:
        consent = GuardianConsent(
            student_id=student.id,
            guardian_name=raw_data.get("guardian_name", "Guardian"),
            guardian_email=raw_data.get("guardian_email", "guardian@example.com"),
            consent_given=bool(consent_given),
            consented_at=datetime.utcnow() if consent_given else None
        )
        db.session.add(consent)
    else:
        consent.consent_given = bool(consent_given)
        consent.consented_at = datetime.utcnow() if consent_given else None

    db.session.commit()

    return jsonify({
        "message": "Guardian consent updated successfully",
        "student_id": student.id,
        "consent_given": consent.consent_given,
        "consent_timestamp": consent.consented_at.isoformat() if consent.consented_at else None
    }), 200
