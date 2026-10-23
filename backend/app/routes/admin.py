import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from app.db_models import User, Student, Subject, GradeLevel, SystemSetting, LearningSession
from app.schemas.settings_schema import KNOWN_SETTINGS
from app.services.csv_importer import parse_and_validate_csv
from app.services.user_service import create_user_from_data
from app.utils.decorators import role_required
from app.extensions import db

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/users", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_users():
    role_filter = request.args.get("role", "").strip().lower()
    search_query = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    per_page = max(1, min(per_page, 100))
    page = max(1, page)

    # Eagerly load student profiles and consent to avoid N+1 queries
    query = User.query.options(
        joinedload(User.student_profile).joinedload(Student.guardian_consent)
    )

    # Filter by role if explicitly provided (unrecognized role params are intentionally ignored to return all)
    if role_filter and role_filter in ["admin", "teacher", "student"]:
        query = query.filter(User.role == role_filter)

    # Search filter across email, first_name, and last_name
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                User.email.ilike(search_pattern),
                User.first_name.ilike(search_pattern),
                User.last_name.ilike(search_pattern)
            )
        )

    query = query.order_by(User.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    users_list = []
    for user in pagination.items:
        u_dict = user.to_dict()
        if user.role == "student" and user.student_profile:
            u_dict["pseudonym_id"] = user.student_profile.pseudonym_id
            if user.student_profile.guardian_consent:
                u_dict["guardian_consent_given"] = user.student_profile.guardian_consent.consent_given
        users_list.append(u_dict)

    return jsonify({
        "users": users_list,
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages
    }), 200


@admin_bp.route("/users/<int:user_id>/status", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_user_status(user_id):
    raw_data = request.get_json(silent=True)
    if not raw_data or "is_active" not in raw_data:
        return jsonify({"error": "Missing 'is_active' boolean field in JSON body"}), 400

    raw_value = raw_data["is_active"]
    if not isinstance(raw_value, bool):
        return jsonify({"error": "'is_active' must be a JSON boolean (true/false), not a string"}), 400
    
    is_active = raw_value
    target_user = User.query.get_or_404(user_id)

    # Edge case protection: Admin cannot deactivate their own account
    current_admin_id = get_jwt_identity()
    if str(target_user.id) == str(current_admin_id) and not is_active:
        return jsonify({"error": "Admin accounts cannot deactivate their own account."}), 400

    target_user.is_active = is_active
    db.session.commit()

    return jsonify(target_user.to_dict()), 200


@admin_bp.route("/users/bulk-import", methods=["POST"])
@jwt_required()
@role_required("admin")
def bulk_import_users():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded under key 'file'"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "Selected file is empty"}), 400

    admin_id = get_jwt_identity()
    created_by_id = int(admin_id) if str(admin_id).isdigit() else None

    # Query valid grade level names once to keep parse_and_validate_csv pure without per-row DB queries
    valid_grade_names = set(gl.name for gl in GradeLevel.query.all())

    # Step 1: Pure parsing and validation
    parsed = parse_and_validate_csv(file.stream, valid_grade_names=valid_grade_names)

    created = 0
    failed_count = len(parsed["errors"])
    errors = list(parsed["errors"])
    created_users = []

    # Step 2: Atomic per-row creation
    for row in parsed["valid_rows"]:
        existing_user = User.query.filter_by(email=row["email"]).first()
        if existing_user:
            failed_count += 1
            errors.append({
                "row_number": row["row_number"],
                "error": f"A user with email '{row['email']}' already exists in database"
            })
            continue

        try:
            new_user = create_user_from_data(row, created_by_id=created_by_id)
            db.session.commit()
            created += 1
            created_users.append(new_user.to_dict())
        except Exception as e:
            db.session.rollback()
            failed_count += 1
            errors.append({
                "row_number": row["row_number"],
                "error": f"Creation failed: {str(e)}"
            })

    errors = sorted(errors, key=lambda x: x["row_number"])

    return jsonify({
        "created": created,
        "failed": failed_count,
        "errors": errors,
        "created_users": created_users
    }), 200


@admin_bp.route("/dashboard/stats", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_dashboard_stats():
    role_counts = db.session.query(User.role, func.count(User.id)).group_by(User.role).all()
    counts = {role: count for role, count in role_counts}

    total_users = sum(counts.values())
    total_courses = Subject.query.filter_by(is_archived=False).count()

    active_sessions = LearningSession.query.filter(LearningSession.end_time.is_(None)).count()

    upload_folder = current_app.config.get("UPLOAD_FOLDER", os.path.join(current_app.root_path, "..", "uploads"))
    total_bytes = 0
    if os.path.exists(upload_folder):
        for root, dirs, files in os.walk(upload_folder):
            for f in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    storage_used_mb = round(total_bytes / (1024 * 1024), 2)

    return jsonify({
        "total_users": total_users,
        "total_admins": counts.get("admin", 0),
        "total_teachers": counts.get("teacher", 0),
        "total_students": counts.get("student", 0),
        "active_sessions": active_sessions,
        "total_courses": total_courses,
        "storage_used_mb": storage_used_mb,
        "note": None
    }), 200


# NOTE: SystemSetting database values are stored for admin configuration (FR-ADM-05);
# runtime interventionEngine consumption will be wired when the live monitoring pipeline is connected.

@admin_bp.route("/settings", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_settings():
    settings = SystemSetting.query.all()
    setting_map = {s.key: s.value for s in settings}

    # Default fallback values
    defaults = {
        "intervention_min_cooldown_seconds": "30",
        "intervention_max_cooldown_seconds": "120",
        "data_retention_days": "90",
    }
    for k, v in defaults.items():
        if k not in setting_map:
            setting_map[k] = v

    return jsonify(setting_map), 200


@admin_bp.route("/settings", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_settings():
    raw_data = request.get_json(silent=True)
    if not raw_data or not isinstance(raw_data, dict):
        return jsonify({"error": "Missing JSON request dictionary body"}), 400

    payload = raw_data.get("settings", raw_data) if isinstance(raw_data.get("settings"), dict) else raw_data

    errors = []
    validated_updates = {}

    # Reject unknown setting keys
    for key in payload.keys():
        if key not in KNOWN_SETTINGS:
            errors.append(f"Unknown setting key: '{key}'")

    existing = {s.key: s.value for s in SystemSetting.query.all()}

    new_min_val = payload.get("intervention_min_cooldown_seconds", existing.get("intervention_min_cooldown_seconds", "30"))
    new_max_val = payload.get("intervention_max_cooldown_seconds", existing.get("intervention_max_cooldown_seconds", "120"))

    try:
        target_min = int(str(new_min_val).strip())
    except ValueError:
        target_min = 30

    try:
        target_max = int(str(new_max_val).strip())
    except ValueError:
        target_max = 120

    for key, val in payload.items():
        if key not in KNOWN_SETTINGS:
            continue

        rules = KNOWN_SETTINGS[key]
        val_str = str(val).strip()

        if rules["type"] == int:
            try:
                val_int = int(val_str)
                if val_int < rules["min"] or val_int > rules["max"]:
                    errors.append(f"{key} must be an integer between {rules['min']} and {rules['max']}")
                elif key == "intervention_min_cooldown_seconds" and val_int > target_max:
                    errors.append("intervention_min_cooldown_seconds cannot exceed intervention_max_cooldown_seconds")
                elif key == "intervention_max_cooldown_seconds" and val_int < target_min:
                    errors.append("intervention_max_cooldown_seconds cannot be smaller than intervention_min_cooldown_seconds")
                else:
                    validated_updates[key] = str(val_int)
            except ValueError:
                errors.append(f"{key} must be a valid integer")

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    for k, v in validated_updates.items():
        db.session.merge(SystemSetting(key=k, value=v))

    db.session.commit()

    settings = SystemSetting.query.all()
    setting_map = {s.key: s.value for s in settings}
    return jsonify(setting_map), 200
