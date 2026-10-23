from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import role_required
from app.db_models import LearningSession, GuardianConsent, Student
from app.schemas import SessionStartSchema, SessionStopSchema
from app.extensions import db
from datetime import datetime

sessions_bp = Blueprint("sessions", __name__)

@sessions_bp.route("/start", methods=["POST"])
@jwt_required()
@role_required("STUDENT", "student")
def start_session():
    data = SessionStartSchema().load(request.json)
    user_id = get_jwt_identity()

    student = Student.query.filter_by(user_id=user_id).first()
    student_id = student.id if student else user_id

    # Check parental consent status (FR-AUTH-06)
    consent = GuardianConsent.query.filter_by(student_id=student_id).first()
    if data.get("is_monitored", True) and (not consent or not consent.consent_given):
        return jsonify({"error": "Parental consent required for monitored sessions"}), 403

    session = LearningSession(
        student_id=student_id,
        module_id=data["module_id"],
        is_monitored=data.get("is_monitored", True)
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        "session_id": session.id,
        "is_monitored": session.is_monitored,
        "start_time": session.start_time.isoformat()
    }), 201

@sessions_bp.route("/stop", methods=["POST"])
@jwt_required()
@role_required("STUDENT", "student")
def stop_session():
    data = SessionStopSchema().load(request.json)
    session = LearningSession.query.get_or_404(data["session_id"])
    session.end_time = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Session stopped", "session_id": session.id}), 200
