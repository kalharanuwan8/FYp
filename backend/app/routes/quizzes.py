from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from pydantic import ValidationError

from app.db_models import (
    Module, 
    Quiz, 
    QuizQuestion, 
    QuizQuestionOption, 
    QuizAttempt, 
    QuizAnswer, 
    ModuleContent, 
    Enrollment, 
    Student
)
from app.schemas.quiz_schema import QuizCreateSchema, AttemptSubmitSchema
from app.routes.courses import is_teacher_owner_of_module
from app.utils.decorators import role_required
from app.extensions import db

quizzes_bp = Blueprint("quizzes", __name__)

def format_validation_errors(err: ValidationError):
    details = []
    for e in err.errors():
        field = "->".join(str(x) for x in e["loc"]) if e["loc"] else "body"
        details.append({"field": field, "message": e["msg"]})
    return details

def serialize_quiz_for_user(quiz, reveal_answers: bool):
    data = quiz.to_dict(include_questions=False)
    questions_list = []
    for q in quiz.questions:
        q_dict = {
            "id": q.id,
            "quiz_id": q.quiz_id,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "sequence_order": q.sequence_order,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        if reveal_answers:
            q_dict["correct_answer_text"] = q.correct_answer_text

        options_list = []
        for opt in q.options:
            opt_dict = {
                "id": opt.id,
                "question_id": opt.question_id,
                "option_text": opt.option_text,
            }
            if reveal_answers:
                opt_dict["is_correct"] = opt.is_correct
            options_list.append(opt_dict)
        q_dict["options"] = options_list
        questions_list.append(q_dict)

    data["questions"] = questions_list
    return data


@quizzes_bp.route("/modules/<int:module_id>/quizzes", methods=["POST"])
@jwt_required()
@role_required("teacher")
def create_quiz(module_id):
    user_id = int(get_jwt_identity())
    if not is_teacher_owner_of_module(user_id, module_id):
        return jsonify({"error": "Forbidden: You are not assigned to manage this course module"}), 403

    module = db.session.get(Module, module_id)
    if not module:
        return jsonify({"error": "Module not found"}), 404

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = QuizCreateSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    try:
        # 1. Create Quiz
        new_quiz = Quiz(
            module_id=module_id,
            title=data.title
        )
        db.session.add(new_quiz)
        db.session.flush()

        # 2. Create Questions & Options (sequence_order assigned server-side sequentially)
        for idx, q_data in enumerate(data.questions, start=1):
            new_question = QuizQuestion(
                quiz_id=new_quiz.id,
                question_text=q_data.question_text,
                question_type=q_data.question_type,
                correct_answer_text=q_data.correct_answer_text,
                sequence_order=idx
            )
            db.session.add(new_question)
            db.session.flush()

            if q_data.question_type == "multiple_choice" and q_data.options:
                for opt_data in q_data.options:
                    new_option = QuizQuestionOption(
                        question_id=new_question.id,
                        option_text=opt_data.option_text,
                        is_correct=opt_data.is_correct
                    )
                    db.session.add(new_option)

        # 3. Dual-linkage: Create ModuleContent entry for quiz
        module_content = ModuleContent(
            module_id=module_id,
            content_type="quiz",
            title=new_quiz.title,
            quiz_id=new_quiz.id
        )
        db.session.add(module_content)

        db.session.commit()
        return jsonify(serialize_quiz_for_user(new_quiz, reveal_answers=True)), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to create quiz"}), 500


@quizzes_bp.route("/modules/<int:module_id>/quizzes", methods=["GET"])
@jwt_required()
def list_module_quizzes(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return jsonify({"error": "Module not found"}), 404

    claims = get_jwt()
    role = str(claims.get("role", "")).lower()
    user_id = int(get_jwt_identity())

    # Check student enrollment / teacher ownership
    if role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found"}), 403
        enrollment = Enrollment.query.filter_by(student_id=student.id, subject_id=module.subject_id).first()
        if not enrollment:
            return jsonify({"error": "Forbidden: You are not enrolled in this course"}), 403
    elif role == "teacher":
        if not is_teacher_owner_of_module(user_id, module_id):
            return jsonify({"error": "Forbidden: You are not assigned to manage this course module"}), 403
    elif role != "admin":
        return jsonify({"error": "Forbidden"}), 403

    reveal_answers = (role == "admin") or (role == "teacher" and is_teacher_owner_of_module(user_id, module_id))
    quizzes = Quiz.query.filter_by(module_id=module_id).order_by(Quiz.id.asc()).all()

    return jsonify([serialize_quiz_for_user(q, reveal_answers=reveal_answers) for q in quizzes]), 200


@quizzes_bp.route("/quizzes/<int:quiz_id>", methods=["GET"])
@jwt_required()
def get_quiz_detail(quiz_id):
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404

    claims = get_jwt()
    role = str(claims.get("role", "")).lower()
    user_id = int(get_jwt_identity())

    module = db.session.get(Module, quiz.module_id)

    # Check student enrollment / teacher ownership
    if role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found"}), 403
        enrollment = Enrollment.query.filter_by(student_id=student.id, subject_id=module.subject_id).first()
        if not enrollment:
            return jsonify({"error": "Forbidden: You are not enrolled in this course"}), 403
    elif role == "teacher":
        if not is_teacher_owner_of_module(user_id, quiz.module_id):
            return jsonify({"error": "Forbidden: You are not assigned to manage this course module"}), 403
    elif role != "admin":
        return jsonify({"error": "Forbidden"}), 403

    reveal_answers = (role == "admin") or (role == "teacher" and is_teacher_owner_of_module(user_id, quiz.module_id))
    return jsonify(serialize_quiz_for_user(quiz, reveal_answers=reveal_answers)), 200


@quizzes_bp.route("/quizzes/<int:quiz_id>/attempts", methods=["POST"])
@jwt_required()
@role_required("student")
def start_quiz_attempt(quiz_id):
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404

    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    module = db.session.get(Module, quiz.module_id)
    enrollment = Enrollment.query.filter_by(student_id=student.id, subject_id=module.subject_id).first()
    if not enrollment:
        return jsonify({"error": "Forbidden: You are not enrolled in this course"}), 403

    # Check single-attempt policy
    existing_completed = QuizAttempt.query.filter_by(
        quiz_id=quiz_id, 
        student_id=student.id
    ).filter(QuizAttempt.completed_at.isnot(None)).first()

    if existing_completed:
        return jsonify({"error": "Forbidden: You have already completed an attempt for this quiz"}), 403

    new_attempt = QuizAttempt(
        quiz_id=quiz_id,
        student_id=student.id,
        started_at=datetime.utcnow()
    )
    db.session.add(new_attempt)
    db.session.commit()

    return jsonify({
        "attempt_id": new_attempt.id,
        "quiz_id": quiz_id,
        "started_at": new_attempt.started_at.isoformat()
    }), 201


@quizzes_bp.route("/attempts/<int:attempt_id>/submit", methods=["POST"])
@jwt_required()
@role_required("student")
def submit_quiz_attempt(attempt_id):
    attempt = db.session.get(QuizAttempt, attempt_id)
    if not attempt:
        return jsonify({"error": "Quiz attempt not found"}), 404

    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student or attempt.student_id != student.id:
        return jsonify({"error": "Forbidden: You do not own this quiz attempt"}), 403

    if attempt.completed_at is not None:
        return jsonify({"error": "Forbidden: Quiz attempt has already been submitted"}), 400

    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"error": "Missing JSON request body"}), 400

    try:
        data = AttemptSubmitSchema.model_validate(raw_data)
    except ValidationError as err:
        return jsonify({"error": "Validation failed", "details": format_validation_errors(err)}), 400

    quiz = db.session.get(Quiz, attempt.quiz_id)
    questions_by_id = {q.id: q for q in quiz.questions}
    total_questions = len(questions_by_id)
    if total_questions == 0:
        return jsonify({"error": "Quiz has no questions to grade"}), 400

    correct_count = 0
    seen_question_ids = set()

    try:
        for ans_data in data.answers:
            q_id = ans_data.question_id
            if q_id in seen_question_ids:
                continue
            seen_question_ids.add(q_id)

            question = questions_by_id.get(q_id)
            if not question:
                continue

            is_correct = False

            if question.question_type == "multiple_choice":
                if ans_data.selected_option_id:
                    option = db.session.get(QuizQuestionOption, ans_data.selected_option_id)
                    if option and option.question_id == question.id and option.is_correct:
                        is_correct = True
            elif question.question_type == "short_answer":
                user_text = (ans_data.answer_text or "").strip().lower()
                target_text = (question.correct_answer_text or "").strip().lower()
                if user_text and target_text and user_text == target_text:
                    is_correct = True

            if is_correct:
                correct_count += 1

            new_answer = QuizAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_option_id=ans_data.selected_option_id,
                answer_text=ans_data.answer_text,
                is_correct=is_correct,
                answered_at=datetime.utcnow()
            )
            db.session.add(new_answer)

        # Calculate final percentage score
        score = round((correct_count / float(total_questions)) * 100.0, 2)
        attempt.score = score
        attempt.completed_at = datetime.utcnow()

        db.session.commit()

        gamification = {}
        try:
            from app.services.gamification_service import award_quiz_xp
            gamification = award_quiz_xp(
                student.id,
                correct_count=correct_count,
                total_questions=total_questions,
            )
        except Exception:
            gamification = {}

        remediation = None
        try:
            from app.services.remediation_service import build_remediation_for_attempt
            remediation = build_remediation_for_attempt(
                student_id=student.id,
                quiz=quiz,
                attempt_id=attempt.id,
                correct_count=correct_count,
                total_questions=total_questions,
            )
        except Exception:
            import traceback
            traceback.print_exc()
            remediation = None

        payload = attempt.to_dict(include_answers=True)
        payload["xp_gained"] = gamification.get("xp_gained", 0)
        payload["new_badges"] = gamification.get("new_badges", [])
        payload["progress"] = gamification.get("progress")
        payload["correct_count"] = correct_count
        payload["total_questions"] = total_questions
        payload["remediation"] = remediation
        return jsonify(payload), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to grade quiz attempt"}), 500


@quizzes_bp.route("/remediation/<int:event_id>/choice", methods=["POST"])
@jwt_required()
@role_required("student")
def record_remediation_choice(event_id):
    from app.db_models.remediation import RemediationEvent
    from app.services.remediation_service import VALID_CHOICES

    event = db.session.get(RemediationEvent, event_id)
    if not event:
        return jsonify({"error": "Remediation event not found"}), 404

    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student or event.student_id != student.id:
        return jsonify({"error": "Forbidden"}), 403

    raw = request.get_json(silent=True) or {}
    choice = raw.get("choice")
    if choice not in VALID_CHOICES:
        return jsonify({
            "error": "Invalid choice",
            "allowed": sorted(VALID_CHOICES),
        }), 400

    event.student_choice = choice
    event.choice_at = datetime.utcnow()
    db.session.commit()
    return jsonify(event.to_dict()), 200


@quizzes_bp.route("/quizzes/<int:quiz_id>/attempts", methods=["GET"])
@jwt_required()
def list_quiz_attempts(quiz_id):
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404

    claims = get_jwt()
    role = str(claims.get("role", "")).lower()
    user_id = int(get_jwt_identity())

    if role == "admin" or (role == "teacher" and is_teacher_owner_of_module(user_id, quiz.module_id)):
        attempts = QuizAttempt.query.filter_by(quiz_id=quiz_id).order_by(QuizAttempt.id.desc()).all()
        return jsonify([att.to_dict(include_answers=True) for att in attempts]), 200

    if role == "teacher":
        return jsonify({"error": "Forbidden: You are not assigned to manage this course module"}), 403

    if role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found"}), 403
        module = db.session.get(Module, quiz.module_id)
        enrollment = Enrollment.query.filter_by(
            student_id=student.id, subject_id=module.subject_id
        ).first()
        if not enrollment:
            return jsonify({"error": "Forbidden: You are not enrolled in this course"}), 403
        attempts = QuizAttempt.query.filter_by(quiz_id=quiz_id, student_id=student.id).order_by(QuizAttempt.id.desc()).all()
        return jsonify([att.to_dict(include_answers=True) for att in attempts]), 200

    return jsonify({"error": "Forbidden"}), 403
