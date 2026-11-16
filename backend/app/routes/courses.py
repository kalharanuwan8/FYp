import os
from typing import Optional
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.db_models import (
    Subject,
    TeacherSubject,
    Module,
    GradeLevel,
    Teacher,
    ModuleContent,
    ModuleMilestoneItem,
    Quiz,
    QuizQuestion,
    QuizQuestionOption,
    QuizAttempt,
    Student,
    Enrollment,
)
from app.schemas.course_schema import (
    SubjectCreateSchema, 
    SubjectUpdateSchema, 
    ModuleCreateSchema, 
    ModuleUpdateSchema,
    MaterialCreateSchema,
    MaterialUpdateSchema,
    GeneratePackSchema,
)
from app.services.storage_service import allowed_file, save_uploaded_file
from app.services.llm_service import LLMService, LLMUnavailableError
from app.services.grade_access import grade_level_for_student, subject_visible_to_student
from app.utils.decorators import role_required
from app.extensions import db

courses_bp = Blueprint("courses", __name__)

def format_validation_errors(err: ValidationError):
    details = []
    for e in err.errors():
        field = "->".join(str(x) for x in e["loc"]) if e["loc"] else "body"
        details.append({"field": field, "message": e["msg"]})
    return details

def is_teacher_owner_of_subject(user_id: int, subject_id: int) -> bool:
    teacher = Teacher.query.filter_by(user_id=user_id).first()
    if not teacher:
        return False
    ts = TeacherSubject.query.filter_by(teacher_id=teacher.id, subject_id=subject_id).first()
    return ts is not None

def is_teacher_owner_of_module(user_id: int, module_id: int) -> bool:
    module = db.session.get(Module, module_id)
    if not module:
        return False
    return is_teacher_owner_of_subject(user_id, module.subject_id)


def is_teacher_owner_of_material(user_id: int, material_id: int) -> bool:
    content = db.session.get(ModuleContent, material_id)
    if not content:
        return False
    return is_teacher_owner_of_module(user_id, content.module_id)


@courses_bp.route("/grade-levels", methods=["GET"])
@jwt_required()
def list_grade_levels():
    """Only "Grade 1" .. "Grade 12", ordered numerically (stray rows are hidden)."""
    wanted = {f"Grade {i}": i for i in range(1, 13)}
    levels = [gl for gl in GradeLevel.query.all() if gl.name in wanted]
    levels.sort(key=lambda gl: wanted[gl.name])
    return jsonify([gl.to_dict() for gl in levels]), 200


@courses_bp.route("/upload", methods=["POST"])
@jwt_required()
@role_required("teacher")
def upload_material_file():
    if "file" not in request.files:
        return jsonify({"error": "No file field found in request"}), 400

    file_obj = request.files["file"]
    if not file_obj or file_obj.filename == "":
        return jsonify({"error": "No file selected for upload"}), 400

    try:
        upload_folder = current_app.config.get("UPLOAD_FOLDER", os.path.join(current_app.root_path, "..", "uploads"))
        saved_rel_path = save_uploaded_file(file_obj, upload_folder)
        return jsonify({
            "file_url": saved_rel_path,
            "filename": os.path.basename(saved_rel_path)
        }), 201
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    except Exception as err:
        return jsonify({"error": f"File save failed: {str(err)}"}), 500


@courses_bp.route("/subjects", methods=["POST"])
@jwt_required()
@role_required("teacher")
def create_subject():
    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = SubjectCreateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    grade_level = db.session.get(GradeLevel, data.grade_level_id)
    if not grade_level:
        return jsonify({"error": f"GradeLevel with id {data.grade_level_id} does not exist"}), 400

    user_id = int(get_jwt_identity())
    teacher = Teacher.query.filter_by(user_id=user_id).first()
    if not teacher:
        return jsonify({"error": "Teacher profile not found for user"}), 403

    try:
        new_subject = Subject(
            title=data.title,
            description=data.description,
            grade_level_id=data.grade_level_id,
            is_archived=False
        )
        db.session.add(new_subject)
        db.session.flush()

        new_ts = TeacherSubject(
            teacher_id=teacher.id,
            subject_id=new_subject.id
        )
        db.session.add(new_ts)
        db.session.commit()

        return jsonify(new_subject.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create subject: {str(e)}"}), 500


@courses_bp.route("/subjects", methods=["GET"])
@jwt_required()
def list_subjects():
    claims = get_jwt()
    role = str(claims.get("role", "")).lower()
    user_id = int(get_jwt_identity())

    search_query = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    per_page = max(1, min(per_page, 100))
    page = max(1, page)

    query = Subject.query

    if role == "teacher":
        teacher = Teacher.query.filter_by(user_id=user_id).first()
        if not teacher:
            return jsonify({"subjects": [], "total": 0, "page": page, "pages": 0}), 200
        query = query.join(TeacherSubject, Subject.id == TeacherSubject.subject_id).filter(
            TeacherSubject.teacher_id == teacher.id
        )
    elif role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        if not student:
            return jsonify({"subjects": [], "total": 0, "page": page, "pages": 0}), 200

        grade_level = grade_level_for_student(student)
        query = query.filter(Subject.is_archived == False)
        if grade_level:
            query = query.filter(Subject.grade_level_id == grade_level.id)
        else:
            query = query.filter(Subject.id == None)
    else:  # Admin
        query = query.filter(Subject.is_archived == False)

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                Subject.title.ilike(search_pattern),
                Subject.description.ilike(search_pattern)
            )
        )

    query = query.order_by(Subject.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "subjects": [s.to_dict() for s in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages
    }), 200


@courses_bp.route("/subjects/<int:subject_id>", methods=["GET"])
@jwt_required()
def get_subject_detail(subject_id):
    try:
        subject = db.session.get(Subject, subject_id)
        if not subject:
            return jsonify({"error": f"Subject with ID #{subject_id} does not exist"}), 404

        claims = get_jwt()
        role = str(claims.get("role", "")).lower()
        user_id = int(get_jwt_identity())

        # Archived subjects can be viewed by admins or assigned co-teachers
        if subject.is_archived:
            is_admin = role == "admin"
            is_owner = role == "teacher" and is_teacher_owner_of_subject(user_id, subject_id)
            if not (is_admin or is_owner):
                return jsonify({"error": f"Subject #{subject_id} is archived and unavailable"}), 404

        if role == "student":
            student = Student.query.filter_by(user_id=user_id).first()
            if not subject_visible_to_student(student, subject):
                return jsonify({"error": "This course is not available for your grade level"}), 403

        # Students must not receive milestone correct answers in subject detail.
        reveal_answers = (role == "admin") or (
            role == "teacher" and is_teacher_owner_of_subject(user_id, subject_id)
        )
        return jsonify(
            subject.to_dict(
                include_modules=True,
                reveal_milestone_answers=reveal_answers,
            )
        ), 200
    except Exception as err:
        current_app.logger.error(f"Error fetching subject detail for ID {subject_id}: {str(err)}")
        return jsonify({"error": f"Failed to load course #{subject_id}: {str(err)}"}), 500


@courses_bp.route("/subjects/<int:subject_id>", methods=["PATCH"])
@jwt_required()
@role_required("teacher")
def update_subject(subject_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_subject(user_id, subject_id):
        return jsonify({"error": "Forbidden: You are not assigned to co-teach or manage this subject"}), 403

    subject = db.session.get(Subject, subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = SubjectUpdateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    if data.title is not None:
        subject.title = data.title
    if data.description is not None:
        subject.description = data.description
    if data.grade_level_id is not None:
        grade_level = db.session.get(GradeLevel, data.grade_level_id)
        if not grade_level:
            return jsonify({"error": f"GradeLevel with id {data.grade_level_id} does not exist"}), 400
        subject.grade_level_id = data.grade_level_id
    if data.is_archived is not None:
        subject.is_archived = data.is_archived

    db.session.commit()
    return jsonify(subject.to_dict()), 200


@courses_bp.route("/subjects/<int:subject_id>/archive", methods=["PATCH"])
@jwt_required()
@role_required("teacher")
def archive_subject(subject_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_subject(user_id, subject_id):
        return jsonify({"error": "Forbidden: You are not assigned to co-teach or manage this subject"}), 403

    subject = db.session.get(Subject, subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    raw_data = request.get_json(silent=True) or {}
    is_archived = raw_data.get("is_archived", True)
    subject.is_archived = is_archived
    db.session.commit()
    return jsonify(subject.to_dict()), 200


@courses_bp.route("/modules", methods=["POST"])
@courses_bp.route("/subjects/<int:subject_id>/modules", methods=["POST"])
@jwt_required()
@role_required("teacher")
def create_module(subject_id=None):
    raw_data = request.get_json(silent=True) or {}
    if subject_id and "subject_id" not in raw_data:
        raw_data["subject_id"] = subject_id

    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = ModuleCreateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    target_subject_id = subject_id or data.subject_id
    if not target_subject_id:
        return jsonify({"error": "subject_id is required"}), 400

    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_subject(user_id, target_subject_id):
        return jsonify({"error": "Forbidden: You are not assigned to co-teach or manage this subject"}), 403

    subject = db.session.get(Subject, target_subject_id)
    if not subject:
        return jsonify({"error": f"Subject with id {target_subject_id} does not exist"}), 400

    if data.sequence_order is None:
        max_order = db.session.query(db.func.max(Module.sequence_order)).filter_by(subject_id=target_subject_id).scalar()
        next_order = (max_order or 0) + 1
    else:
        next_order = data.sequence_order

    new_module = Module(
        subject_id=target_subject_id,
        title=data.title,
        description=data.description,
        sequence_order=next_order,
        is_archived=False
    )
    db.session.add(new_module)
    db.session.commit()

    return jsonify(new_module.to_dict()), 201


@courses_bp.route("/modules/<int:module_id>", methods=["PATCH"])
@jwt_required()
@role_required("teacher")
def update_module(module_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_module(user_id, module_id):
        return jsonify({"error": "Forbidden: You do not have permission to manage this module"}), 403

    module = db.session.get(Module, module_id)
    if not module:
        return jsonify({"error": "Module not found"}), 404

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = ModuleUpdateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    if data.title is not None:
        module.title = data.title
    if data.description is not None:
        module.description = data.description
    if data.sequence_order is not None:
        module.sequence_order = data.sequence_order
    if data.is_archived is not None:
        module.is_archived = data.is_archived

    db.session.commit()
    return jsonify(module.to_dict()), 200


@courses_bp.route("/materials/generate-pack", methods=["POST"])
@jwt_required()
@role_required("teacher")
def generate_material_pack():
    """Draft summary + milestone quiz items from a teacher description (not saved)."""
    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = GeneratePackSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    llm = LLMService(
        base_url=current_app.config.get("LLM_BASE_URL"),
        model=current_app.config.get("LLM_MODEL"),
    )
    try:
        pack = llm.generate_material_pack(
            description=data.description,
            title=data.title,
            num_questions=data.num_questions or 3,
        )
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    except LLMUnavailableError as err:
        return jsonify({"error": str(err)}), 503

    return jsonify(pack), 200


def _resolve_remediation_target(
    module_id: int, target_id: Optional[int], *, exclude_content_id: Optional[int] = None
):
    """Validate remediation_for_content_id: same module, must be a video, not self."""
    if target_id is None:
        return None, None
    target = db.session.get(ModuleContent, target_id)
    if not target or target.module_id != module_id:
        return None, (
            jsonify({"error": "remediation_for_content_id must refer to a material in this module"}),
            400,
        )
    if target.content_type != "video":
        return None, (
            jsonify({"error": "remediation_for_content_id must refer to a video material"}),
            400,
        )
    if exclude_content_id is not None and target.id == exclude_content_id:
        return None, (
            jsonify({"error": "A material cannot be an alternate for itself"}),
            400,
        )
    return target.id, None


def _write_lesson_quiz_questions(quiz, questions):
    for idx, item in enumerate(questions, start=1):
        question = QuizQuestion(
            quiz_id=quiz.id,
            question_text=item.question.strip(),
            question_type="multiple_choice",
            sequence_order=idx,
            difficulty="medium",
        )
        db.session.add(question)
        db.session.flush()
        for opt_index, text in enumerate(item.options):
            db.session.add(
                QuizQuestionOption(
                    question_id=question.id,
                    option_text=text,
                    is_correct=opt_index == item.correct_option,
                )
            )


def _attach_lesson_quiz(module_id, video, questions):
    """Store a comprehension quiz on the video. Separate from intervention milestones."""
    title = f"{video.title} — lesson check"[:150]
    if video.quiz_id:
        taken = QuizAttempt.query.filter_by(quiz_id=video.quiz_id).first()
        if taken:
            return (
                jsonify(
                    {
                        "error": "Students have already taken this lesson quiz, so its questions cannot be replaced."
                    }
                ),
                400,
            )
        quiz = db.session.get(Quiz, video.quiz_id)
        if quiz:
            for old in list(quiz.questions):
                db.session.delete(old)
            db.session.flush()
            quiz.title = title
            linked = ModuleContent.query.filter_by(
                module_id=module_id, content_type="quiz", quiz_id=quiz.id
            ).first()
            if linked:
                linked.title = title
            _write_lesson_quiz_questions(quiz, questions)
            return None
    quiz = Quiz(module_id=module_id, title=title)
    db.session.add(quiz)
    db.session.flush()
    _write_lesson_quiz_questions(quiz, questions)
    video.quiz_id = quiz.id
    db.session.add(
        ModuleContent(
            module_id=module_id,
            content_type="quiz",
            title=title,
            quiz_id=quiz.id,
        )
    )
    return None


@courses_bp.route("/modules/<int:module_id>/materials", methods=["POST"])
@jwt_required()
@role_required("teacher")
def create_material(module_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_module(user_id, module_id):
        return jsonify({"error": "Forbidden: You do not have permission to add materials to this module"}), 403

    module = db.session.get(Module, module_id)
    if not module:
        return jsonify({"error": f"Module with id {module_id} does not exist"}), 400

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = MaterialCreateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    if data.content_type == "quiz":
        if not data.quiz_id:
            return jsonify({"error": "quiz_id is required when content_type is 'quiz'"}), 400
        quiz = db.session.get(Quiz, data.quiz_id)
        if not quiz:
            return jsonify({"error": f"Quiz with id {data.quiz_id} does not exist"}), 400

    rem_id, rem_err = _resolve_remediation_target(module_id, data.remediation_for_content_id)
    if rem_err:
        return rem_err

    new_content = ModuleContent(
        module_id=module_id,
        content_type=data.content_type,
        title=data.title,
        file_url=data.file_url,
        quiz_id=data.quiz_id,
        summary=data.summary,
        remediation_for_content_id=rem_id,
    )
    db.session.add(new_content)
    db.session.flush()

    if data.milestones:
        for idx, item in enumerate(data.milestones):
            db.session.add(
                ModuleMilestoneItem(
                    module_content_id=new_content.id,
                    question=item.question,
                    options_json=list(item.options),
                    correct_option=item.correct_option,
                    hint_text=item.hint_text,
                    sequence_order=item.sequence_order or (idx + 1),
                    is_active=True,
                )
            )

    if data.content_type == "video" and data.video_quiz:
        quiz_err = _attach_lesson_quiz(module_id, new_content, data.video_quiz)
        if quiz_err:
            db.session.rollback()
            return quiz_err

    db.session.commit()
    return jsonify(new_content.to_dict(include_milestones=True)), 201


@courses_bp.route("/materials/<int:material_id>", methods=["GET"])
@jwt_required()
@role_required("teacher")
def get_material(material_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_material(user_id, material_id):
        return jsonify({"error": "Forbidden: You do not have permission to view this material"}), 403

    content = db.session.get(ModuleContent, material_id)
    if not content:
        return jsonify({"error": "Material not found"}), 404
    return jsonify(content.to_dict(include_milestones=True)), 200


def _can_access_material_file(user_id: int, role: str, content: ModuleContent) -> bool:
    """Teacher owner, admin, or enrolled student may download the file."""
    if role == "admin":
        return True
    if role == "teacher":
        return is_teacher_owner_of_material(user_id, content.id)
    if role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        if not student:
            return False
        module = db.session.get(Module, content.module_id)
        if not module:
            return False
        enrollment = Enrollment.query.filter_by(
            student_id=student.id, subject_id=module.subject_id
        ).first()
        if enrollment is None:
            return False
        subject = db.session.get(Subject, module.subject_id)
        return subject_visible_to_student(student, subject)
    return False


@courses_bp.route("/materials/<int:material_id>/file", methods=["GET"])
@jwt_required()
def download_material_file(material_id):
    """Serve an uploaded material file only to enrolled students or owning teachers."""
    content = db.session.get(ModuleContent, material_id)
    if not content or not content.file_url:
        return jsonify({"error": "Material file not found"}), 404

    claims = get_jwt()
    role = str(claims.get("role", "")).lower()
    user_id = int(get_jwt_identity())
    if not _can_access_material_file(user_id, role, content):
        return jsonify({"error": "Forbidden: You do not have access to this material"}), 403

    # Stored as /uploads/<unique_name> (or absolute URL — only local uploads are served).
    file_url = content.file_url
    if file_url.startswith("http://") or file_url.startswith("https://"):
        return jsonify({"error": "External material URLs are not proxied"}), 400
    filename = os.path.basename(file_url)
    if not filename or filename in {".", ".."}:
        return jsonify({"error": "Invalid material path"}), 400

    upload_folder = current_app.config.get(
        "UPLOAD_FOLDER", os.path.join(current_app.root_path, "..", "uploads")
    )
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(current_app.root_path, "..", upload_folder)
    return send_from_directory(upload_folder, filename)


@courses_bp.route("/materials/<int:material_id>", methods=["PATCH"])
@jwt_required()
@role_required("teacher")
def update_material(material_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_material(user_id, material_id):
        return jsonify({"error": "Forbidden: You do not have permission to edit this material"}), 403

    content = db.session.get(ModuleContent, material_id)
    if not content:
        return jsonify({"error": "Material not found"}), 404

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = MaterialUpdateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    next_type = data.content_type if data.content_type is not None else content.content_type
    next_quiz_id = data.quiz_id if "quiz_id" in raw_data else content.quiz_id

    if next_type == "quiz" and not next_quiz_id:
        return jsonify({"error": "quiz_id is required when content_type is 'quiz'"}), 400
    if next_type == "video":
        # The lesson quiz is stored on the video. Editing the file must not clear it.
        next_quiz_id = content.quiz_id
    elif next_type != "quiz":
        next_quiz_id = None

    if data.video_quiz and next_type != "video":
        return jsonify({"error": "video_quiz is only allowed on a video"}), 400

    if data.title is not None:
        content.title = data.title
    if data.content_type is not None:
        content.content_type = data.content_type
    if "file_url" in raw_data:
        content.file_url = data.file_url
    if "summary" in raw_data:
        content.summary = data.summary
    if "remediation_for_content_id" in raw_data:
        rem_id, rem_err = _resolve_remediation_target(
            content.module_id,
            data.remediation_for_content_id,
            exclude_content_id=content.id,
        )
        if rem_err:
            return rem_err
        if next_type == "quiz":
            content.remediation_for_content_id = None
        else:
            content.remediation_for_content_id = rem_id
    content.quiz_id = next_quiz_id

    if data.milestones is not None:
        # Replace bank items with the reviewed list from the teacher
        for old in list(content.milestone_items):
            db.session.delete(old)
        db.session.flush()
        for idx, item in enumerate(data.milestones):
            db.session.add(
                ModuleMilestoneItem(
                    module_content_id=content.id,
                    question=item.question,
                    options_json=list(item.options),
                    correct_option=item.correct_option,
                    hint_text=item.hint_text,
                    sequence_order=item.sequence_order or (idx + 1),
                    is_active=True,
                )
            )

    if next_type == "video" and data.video_quiz:
        quiz_err = _attach_lesson_quiz(content.module_id, content, data.video_quiz)
        if quiz_err:
            db.session.rollback()
            return quiz_err

    db.session.commit()
    return jsonify(content.to_dict(include_milestones=True)), 200


@courses_bp.route("/materials/<int:material_id>", methods=["DELETE"])
@jwt_required()
@role_required("teacher")
def delete_material(material_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_material(user_id, material_id):
        return jsonify({"error": "Forbidden: You do not have permission to delete this material"}), 403

    content = db.session.get(ModuleContent, material_id)
    if not content:
        return jsonify({"error": "Material not found"}), 404

    db.session.delete(content)
    db.session.commit()
    return jsonify({"message": "Material deleted", "id": material_id}), 200


@courses_bp.route("/my-enrollments", methods=["GET"])
@jwt_required()
@role_required("student")
def list_my_enrollments():
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"enrollments": []}), 200

    enrollments = Enrollment.query.filter_by(student_id=student.id).all()
    res = []
    for e in enrollments:
        if subject_visible_to_student(student, e.subject):
            res.append(e.subject.to_dict())

    return jsonify({"enrollments": res}), 200


@courses_bp.route("/subjects/<int:subject_id>/enroll", methods=["POST"])
@jwt_required()
@role_required("student")
def enroll_student_in_subject(subject_id):
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found for user"}), 403

    subject = db.session.get(Subject, subject_id)
    if not subject:
        return jsonify({"error": f"Subject with id {subject_id} does not exist"}), 404

    if subject.is_archived:
        return jsonify({"error": "Cannot enroll in an archived subject"}), 400

    if not subject_visible_to_student(student, subject):
        return jsonify({"error": "This course is not available for your grade level"}), 403

    existing_enrollment = Enrollment.query.filter_by(student_id=student.id, subject_id=subject_id).first()
    if existing_enrollment:
        return jsonify({"error": "Student is already enrolled in this subject"}), 409

    new_enrollment = Enrollment(
        student_id=student.id,
        subject_id=subject_id
    )
    db.session.add(new_enrollment)
    db.session.commit()

    return jsonify({
        "message": f"Successfully enrolled in subject '{subject.title}'",
        "enrollment_id": new_enrollment.id,
        "subject_id": subject_id
    }), 201


@courses_bp.route("/subjects/<int:subject_id>/enroll", methods=["DELETE"])
@jwt_required()
@role_required("student")
def unenroll_student_from_subject(subject_id):
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found for user"}), 403

    enrollment = Enrollment.query.filter_by(student_id=student.id, subject_id=subject_id).first()
    if not enrollment:
        return jsonify({"error": "Enrollment not found"}), 404

    db.session.delete(enrollment)
    db.session.commit()

    return jsonify({"message": f"Successfully unenrolled from subject #{subject_id}"}), 200


@courses_bp.route("/subjects/<int:subject_id>/intervention-config", methods=["GET"])
@jwt_required()
@role_required("teacher")
def get_intervention_config(subject_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_subject(user_id, subject_id):
        return jsonify({"error": "Forbidden: You are not assigned to co-teach or manage this subject"}), 403

    subject = db.session.get(Subject, subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    from app.db_models import InterventionConfig
    cfg = InterventionConfig.query.filter_by(subject_id=subject_id).first()
    if not cfg:
        cfg = InterventionConfig(subject_id=subject_id)
        db.session.add(cfg)
        db.session.commit()
    return jsonify(cfg.to_dict()), 200


@courses_bp.route("/subjects/<int:subject_id>/intervention-config", methods=["PATCH"])
@jwt_required()
@role_required("teacher")
def update_intervention_config(subject_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_subject(user_id, subject_id):
        return jsonify({"error": "Forbidden: You are not assigned to co-teach or manage this subject"}), 403

    subject = db.session.get(Subject, subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    raw = request.get_json(silent=True) or {}
    from app.db_models import InterventionConfig
    cfg = InterventionConfig.query.filter_by(subject_id=subject_id).first()
    if not cfg:
        cfg = InterventionConfig(subject_id=subject_id)
        db.session.add(cfg)

    for key in ("tier1_enabled", "tier2_enabled", "tier3_enabled", "tier4_enabled"):
        if key in raw:
            cfg.__setattr__(key, bool(raw[key]))

    db.session.commit()
    return jsonify(cfg.to_dict()), 200
