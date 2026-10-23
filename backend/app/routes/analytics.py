from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.db_models import (
    User,
    Student,
    Teacher,
    Subject,
    TeacherSubject,
    Module,
    ModuleContent,
    Enrollment,
    QuizAttempt,
    LearningSession,
)
from app.services.focus_metrics import average_focus_percentage
from app.utils.decorators import role_required

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/teacher", methods=["GET"])
@jwt_required()
@role_required("teacher")
def get_teacher_analytics():
    user_id = int(get_jwt_identity())
    teacher = Teacher.query.filter_by(user_id=user_id).first()
    if not teacher:
        return jsonify({"error": "Teacher profile not found"}), 403

    teacher_subjects = Subject.query.join(
        TeacherSubject, Subject.id == TeacherSubject.subject_id
    ).filter(
        TeacherSubject.teacher_id == teacher.id,
        Subject.is_archived == False,
    ).all()

    subject_ids = [s.id for s in teacher_subjects]

    if not subject_ids:
        return jsonify({
            "total_students": 0,
            "total_sessions": 0,
            "avg_focus_percentage": 0.0,
            "avg_quiz_score": 0.0,
            "subject_breakdown": [],
        }), 200

    total_students = Enrollment.query.filter(Enrollment.subject_id.in_(subject_ids)).count()

    modules = Module.query.filter(Module.subject_id.in_(subject_ids)).all()
    module_ids = [m.id for m in modules]

    sessions = (
        LearningSession.query.filter(LearningSession.module_id.in_(module_ids)).all()
        if module_ids
        else []
    )
    total_sessions = len(sessions)
    avg_focus_percentage = average_focus_percentage(sessions)

    avg_quiz_score = 0.0
    if module_ids:
        quizzes = ModuleContent.query.filter(
            ModuleContent.module_id.in_(module_ids),
            ModuleContent.quiz_id.isnot(None),
        ).all()
        quiz_ids = [q.quiz_id for q in quizzes if q.quiz_id]
        if quiz_ids:
            attempts = QuizAttempt.query.filter(
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.completed_at.isnot(None),
            ).all()
            if attempts:
                avg_quiz_score = round(sum(a.score for a in attempts) / len(attempts), 1)

    subject_breakdown = []
    for subj in teacher_subjects:
        enrolled_cnt = Enrollment.query.filter_by(subject_id=subj.id).count()
        subj_modules = [m for m in modules if m.subject_id == subj.id]
        subj_mod_ids = [m.id for m in subj_modules]

        subj_sessions = [s for s in sessions if s.module_id in subj_mod_ids]
        subj_focus = average_focus_percentage(subj_sessions)

        subj_quiz_avg = 0.0
        if subj_mod_ids:
            s_quizzes = ModuleContent.query.filter(
                ModuleContent.module_id.in_(subj_mod_ids),
                ModuleContent.quiz_id.isnot(None),
            ).all()
            s_quiz_ids = [q.quiz_id for q in s_quizzes if q.quiz_id]
            if s_quiz_ids:
                s_attempts = QuizAttempt.query.filter(
                    QuizAttempt.quiz_id.in_(s_quiz_ids),
                    QuizAttempt.completed_at.isnot(None),
                ).all()
                if s_attempts:
                    subj_quiz_avg = round(
                        sum(a.score for a in s_attempts) / len(s_attempts), 1
                    )

        gl_name = subj.grade_level.name if subj.grade_level else "Standard Grade"
        subject_breakdown.append({
            "subject_id": subj.id,
            "title": subj.title,
            "grade_level_name": gl_name,
            "enrolled_students": enrolled_cnt,
            "avg_focus_percentage": subj_focus,
            "avg_quiz_score": subj_quiz_avg,
        })

    return jsonify({
        "total_students": total_students,
        "total_sessions": total_sessions,
        "avg_focus_percentage": avg_focus_percentage,
        "avg_quiz_score": avg_quiz_score,
        "subject_breakdown": subject_breakdown,
    }), 200


@analytics_bp.route("/student", methods=["GET"])
@jwt_required()
@role_required("student")
def get_student_analytics():
    user_id = int(get_jwt_identity())
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 403

    enrollments = Enrollment.query.filter_by(student_id=student.id).all()
    enrolled_subject_ids = [e.subject_id for e in enrollments]

    sessions = LearningSession.query.filter_by(student_id=student.id).all()

    total_study_seconds = 0
    for s in sessions:
        if s.start_time and s.end_time:
            total_study_seconds += int((s.end_time - s.start_time).total_seconds())

    total_study_minutes = round(total_study_seconds / 60.0, 1)
    avg_focus_percentage = average_focus_percentage(sessions)

    attempts = QuizAttempt.query.filter_by(student_id=student.id).filter(
        QuizAttempt.completed_at.isnot(None)
    ).all()
    avg_quiz_score = 0.0
    if attempts:
        avg_quiz_score = round(sum(a.score for a in attempts) / len(attempts), 1)

    subject_progress = []
    for sub_id in enrolled_subject_ids:
        subject = db.session.get(Subject, sub_id)
        if subject and not subject.is_archived:
            subj_modules = Module.query.filter_by(subject_id=subject.id).all()
            subj_mod_ids = [m.id for m in subj_modules]

            s_sessions = [s for s in sessions if s.module_id in subj_mod_ids]
            s_focus = average_focus_percentage(s_sessions)

            gl_name = subject.grade_level.name if subject.grade_level else "Standard Grade"
            subject_progress.append({
                "subject_id": subject.id,
                "title": subject.title,
                "grade_level_name": gl_name,
                "sessions_count": len(s_sessions),
                "avg_focus_percentage": s_focus,
            })

    return jsonify({
        "total_study_minutes": total_study_minutes,
        "total_sessions": len(sessions),
        "avg_focus_percentage": avg_focus_percentage,
        "avg_quiz_score": avg_quiz_score,
        "completed_quizzes": len(attempts),
        "subject_progress": subject_progress,
    }), 200


@analytics_bp.route("/admin", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_admin_analytics():
    total_users = User.query.count()
    total_students = Student.query.count()
    total_teachers = Teacher.query.count()
    total_subjects = Subject.query.filter_by(is_archived=False).count()
    sessions = LearningSession.query.all()
    total_sessions = len(sessions)
    platform_avg_focus = average_focus_percentage(sessions)

    completed_quizzes = QuizAttempt.query.filter(
        QuizAttempt.completed_at.isnot(None)
    ).count()

    return jsonify({
        "total_users": total_users,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_subjects": total_subjects,
        "total_sessions": total_sessions,
        "platform_avg_focus": platform_avg_focus,
        "completed_quizzes": completed_quizzes,
    }), 200
