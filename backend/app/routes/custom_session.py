"""Upload a personal file and run the monitoring pipeline on it."""
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.db_models import CustomUpload, GuardianConsent, LearningSession, Student
from app.extensions import db
from app.routes.session import (
    SESSION_ENGINES,
    SESSION_NOISE_MONITORS,
    _close_open_sessions,
    _engine_for_session,
)
from app.services.custom_session import (
    CUSTOM_EXTENSIONS,
    content_kind_for,
    ensure_custom_module,
    title_from_filename,
)
from app.services.noise_monitor import NoiseMonitor
from app.services.storage_service import save_uploaded_file
from app.utils.decorators import role_required

custom_session_bp = Blueprint("custom_session", __name__)


def _student_or_error():
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return None, (jsonify({"error": "Student profile not found"}), 403)
    return student, None


def _owned_upload(student, upload_id):
    upload = db.session.get(CustomUpload, upload_id)
    if not upload or upload.student_id != student.id:
        return None
    return upload


@custom_session_bp.route("/uploads", methods=["GET"])
@jwt_required()
@role_required("student")
def list_uploads():
    student, err = _student_or_error()
    if err:
        return err
    rows = (
        CustomUpload.query.filter_by(student_id=student.id)
        .order_by(CustomUpload.created_at.desc())
        .all()
    )
    return jsonify({"uploads": [row.to_dict() for row in rows]}), 200


@custom_session_bp.route("/uploads", methods=["POST"])
@jwt_required()
@role_required("student")
def upload_file():
    student, err = _student_or_error()
    if err:
        return err
    if "file" not in request.files:
        return jsonify({"error": "No file field found in request"}), 400
    file_obj = request.files["file"]
    if not file_obj or not file_obj.filename:
        return jsonify({"error": "No file selected for upload"}), 400

    title = (request.form.get("title") or "").strip()
    if not title:
        title = title_from_filename(file_obj.filename)

    try:
        upload_folder = current_app.config.get(
            "UPLOAD_FOLDER", os.path.join(current_app.root_path, "..", "uploads")
        )
        saved_rel_path = save_uploaded_file(file_obj, upload_folder, allowed=CUSTOM_EXTENSIONS)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"File save failed: {exc}"}), 500

    row = CustomUpload(
        student_id=student.id,
        title=title[:150],
        original_filename=os.path.basename(file_obj.filename)[:255],
        file_url=saved_rel_path,
        content_kind=content_kind_for(file_obj.filename),
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@custom_session_bp.route("/uploads/<int:upload_id>/file", methods=["GET"])
@jwt_required()
@role_required("student")
def download_upload(upload_id):
    student, err = _student_or_error()
    if err:
        return err
    upload = _owned_upload(student, upload_id)
    if not upload:
        return jsonify({"error": "Upload not found"}), 404
    filename = os.path.basename(upload.file_url or "")
    if not filename or filename in {".", ".."}:
        return jsonify({"error": "Invalid upload path"}), 400
    upload_folder = current_app.config.get(
        "UPLOAD_FOLDER", os.path.join(current_app.root_path, "..", "uploads")
    )
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(current_app.root_path, "..", upload_folder)
    return send_from_directory(upload_folder, filename)


@custom_session_bp.route("/uploads/<int:upload_id>", methods=["DELETE"])
@jwt_required()
@role_required("student")
def delete_upload(upload_id):
    student, err = _student_or_error()
    if err:
        return err
    upload = _owned_upload(student, upload_id)
    if not upload:
        return jsonify({"error": "Upload not found"}), 404
    open_session = LearningSession.query.filter_by(
        custom_upload_id=upload.id, end_time=None
    ).first()
    if open_session:
        return jsonify({"error": "Stop the monitoring session before deleting this file"}), 409
    db.session.delete(upload)
    db.session.commit()
    return jsonify({"message": "Upload deleted", "id": upload_id}), 200


@custom_session_bp.route("/start", methods=["POST"])
@jwt_required()
@role_required("student")
def start_custom_session():
    student, err = _student_or_error()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    try:
        upload_id = int(body.get("upload_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "upload_id is required"}), 400

    upload = _owned_upload(student, upload_id)
    if not upload:
        return jsonify({"error": "Upload not found"}), 404

    consent = GuardianConsent.query.filter_by(student_id=student.id).first()
    if not consent or not consent.consent_given:
        return jsonify({"error": "Parental/Guardian consent required for monitored learning sessions"}), 403

    now_dt = datetime.utcnow()
    _close_open_sessions(student.id, now_dt)
    module = ensure_custom_module()
    new_session = LearningSession(
        student_id=student.id,
        module_id=module.id,
        custom_upload_id=upload.id,
        start_time=now_dt,
        is_monitored=True,
    )
    db.session.add(new_session)
    db.session.commit()

    SESSION_ENGINES[new_session.id] = _engine_for_session(new_session)
    SESSION_NOISE_MONITORS[new_session.id] = NoiseMonitor()

    return jsonify({
        "message": "Custom monitoring session started",
        "session_id": new_session.id,
        "student_id": student.id,
        "module_id": module.id,
        "start_time": new_session.start_time.isoformat(),
        "is_monitored": True,
        "session_kind": "custom",
        "interventions": "best",
        "upload": upload.to_dict(),
    }), 201
