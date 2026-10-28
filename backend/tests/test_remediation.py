"""Unit and API tests for post-quiz adaptive remediation."""

from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token

from app.db_models import (
    User,
    Teacher,
    Student,
    GradeLevel,
    Subject,
    TeacherSubject,
    Module,
    ModuleContent,
    ModuleMilestoneItem,
    Enrollment,
    Quiz,
    QuizQuestion,
    QuizQuestionOption,
    LearningSession,
    RemediationEvent,
)
from app.extensions import db
from app.services.observation_coverage import FOCUS_METRIC_VERSION
from app.services.remediation_service import (
    KIND_ALTERNATIVE,
    KIND_GUIDED,
    KIND_PACK,
    PATH_DIFFERENT,
    PATH_GUIDED,
    REASON_ATTENTION,
    REASON_COMPREHENSION,
    REASON_INSUFFICIENT,
    build_offers,
    compute_error_rate,
    decide_reason,
    should_trigger_remediation,
)


def test_error_rate_exactly_50_percent_no_trigger(app):
    with app.app_context():
        rate = compute_error_rate(correct_count=1, total_questions=2)
        assert rate == 0.5
        assert should_trigger_remediation(0.5, has_video=True, threshold=0.50) is False


def test_decide_reason_high_focus_comprehension(app):
    with app.app_context():
        assert decide_reason(50.0, 70.0, coverage_min=50.0, focus_min=70.0) == REASON_COMPREHENSION
        assert decide_reason(80.0, 90.0, coverage_min=50.0, focus_min=70.0) == REASON_COMPREHENSION


def test_decide_reason_low_focus_attention(app):
    with app.app_context():
        assert decide_reason(50.0, 69.9, coverage_min=50.0, focus_min=70.0) == REASON_ATTENTION
        assert decide_reason(90.0, 10.0, coverage_min=50.0, focus_min=70.0) == REASON_ATTENTION


def test_decide_reason_no_session_or_low_coverage(app):
    with app.app_context():
        assert decide_reason(None, None, coverage_min=50.0, focus_min=70.0) == REASON_INSUFFICIENT
        assert decide_reason(49.9, 90.0, coverage_min=50.0, focus_min=70.0) == REASON_INSUFFICIENT
        assert decide_reason(50.0, None, coverage_min=50.0, focus_min=70.0) == REASON_INSUFFICIENT


def _make_content(module_id, content_type, title, summary=None, file_url=None):
    c = ModuleContent(
        module_id=module_id,
        content_type=content_type,
        title=title,
        summary=summary,
        file_url=file_url,
    )
    db.session.add(c)
    db.session.flush()
    return c


def _add_milestone(content_id, question, active=True, order=1):
    m = ModuleMilestoneItem(
        module_content_id=content_id,
        question=question,
        options_json=["A", "B"],
        correct_option=0,
        sequence_order=order,
        is_active=active,
    )
    db.session.add(m)
    db.session.flush()
    return m


def test_content_fallback_a_document_wins(app):
    with app.app_context():
        gl = GradeLevel(name="G-Rem-A")
        db.session.add(gl)
        db.session.flush()
        subj = Subject(title="Subj A", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        mod = Module(subject_id=subj.id, title="Mod A", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        video = _make_content(mod.id, "video", "Vid", summary="pack text")
        _add_milestone(video.id, "Q1")
        doc = _make_content(mod.id, "document", "Slides PDF", file_url="/uploads/x.pdf")
        db.session.commit()

        contents = ModuleContent.query.filter_by(module_id=mod.id).all()
        path, offers = build_offers(REASON_COMPREHENSION, contents)
        assert path == PATH_DIFFERENT
        assert len(offers) == 1
        assert offers[0]["kind"] == KIND_ALTERNATIVE
        assert offers[0]["content_id"] == doc.id


def test_content_fallback_b_approved_pack(app):
    with app.app_context():
        gl = GradeLevel(name="G-Rem-B")
        db.session.add(gl)
        db.session.flush()
        subj = Subject(title="Subj B", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        mod = Module(subject_id=subj.id, title="Mod B", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        video = _make_content(mod.id, "video", "Vid", summary="Teacher-saved summary")
        _add_milestone(video.id, "Checkpoint 1")
        db.session.commit()

        contents = ModuleContent.query.filter_by(module_id=mod.id).all()
        path, offers = build_offers(REASON_COMPREHENSION, contents)
        assert path == PATH_DIFFERENT
        assert len(offers) == 1
        assert offers[0]["kind"] == KIND_PACK
        assert "correct_option" not in offers[0]["milestones"][0]
        assert offers[0]["summary"] == "Teacher-saved summary"


def test_content_fallback_c_guided_rewatch(app):
    with app.app_context():
        gl = GradeLevel(name="G-Rem-C")
        db.session.add(gl)
        db.session.flush()
        subj = Subject(title="Subj C", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        mod = Module(subject_id=subj.id, title="Mod C", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        video = _make_content(mod.id, "video", "Only Video", summary=None)
        db.session.commit()

        contents = ModuleContent.query.filter_by(module_id=mod.id).all()
        path, offers = build_offers(REASON_INSUFFICIENT, contents)
        assert path == PATH_GUIDED
        assert len(offers) == 1
        assert offers[0]["kind"] == KIND_GUIDED
        assert offers[0]["content_id"] == video.id


def test_inactive_milestones_do_not_count_as_pack(app):
    with app.app_context():
        gl = GradeLevel(name="G-Rem-Inact")
        db.session.add(gl)
        db.session.flush()
        subj = Subject(title="Subj Inact", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        mod = Module(subject_id=subj.id, title="Mod Inact", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        video = _make_content(mod.id, "video", "Vid", summary="Has summary but inactive ms")
        _add_milestone(video.id, "Inactive Q", active=False)
        db.session.commit()

        contents = ModuleContent.query.filter_by(module_id=mod.id).all()
        path, offers = build_offers(REASON_COMPREHENSION, contents)
        assert path == PATH_GUIDED
        assert offers[0]["kind"] == KIND_GUIDED


def test_attention_offers_guided_plus_alternative(app):
    with app.app_context():
        gl = GradeLevel(name="G-Rem-Att")
        db.session.add(gl)
        db.session.flush()
        subj = Subject(title="Subj Att", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        mod = Module(subject_id=subj.id, title="Mod Att", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        video = _make_content(mod.id, "video", "Vid")
        doc = _make_content(mod.id, "document", "Notes", file_url="/uploads/n.pdf")
        db.session.commit()

        contents = ModuleContent.query.filter_by(module_id=mod.id).all()
        path, offers = build_offers(REASON_ATTENTION, contents)
        assert path == PATH_GUIDED
        kinds = [o["kind"] for o in offers]
        assert KIND_GUIDED in kinds
        assert KIND_ALTERNATIVE in kinds


def test_api_failing_quiz_returns_remediation_and_stores_event(client, app):
    with app.app_context():
        gl = GradeLevel(name="G-Rem-API")
        db.session.add(gl)
        db.session.flush()

        t_user = User(
            email="t_rem_api@test.com",
            password="hash",
            role="teacher",
            first_name="T",
            last_name="R",
        )
        st_user = User(
            email="st_rem_api@test.com",
            password="hash",
            role="student",
            first_name="S",
            last_name="R",
        )
        db.session.add(t_user)
        db.session.add(st_user)
        db.session.flush()

        teacher = Teacher(user_id=t_user.id)
        student = Student(user_id=st_user.id)
        db.session.add(teacher)
        db.session.add(student)
        db.session.flush()

        subj = Subject(title="Remediation API Subject", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subj.id))
        db.session.add(Enrollment(student_id=student.id, subject_id=subj.id))
        db.session.flush()

        mod = Module(subject_id=subj.id, title="Video Module", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        video = _make_content(mod.id, "video", "Lesson Video", file_url="/uploads/v.mp4")
        doc = _make_content(
            mod.id, "document", "Lesson Notes", file_url="/uploads/notes.pdf"
        )

        quiz = Quiz(module_id=mod.id, title="Follow-up Quiz")
        db.session.add(quiz)
        db.session.flush()
        db.session.add(
            ModuleContent(
                module_id=mod.id,
                content_type="quiz",
                title=quiz.title,
                quiz_id=quiz.id,
            )
        )

        q1 = QuizQuestion(
            quiz_id=quiz.id,
            question_text="Q1",
            question_type="multiple_choice",
            sequence_order=1,
        )
        q2 = QuizQuestion(
            quiz_id=quiz.id,
            question_text="Q2",
            question_type="multiple_choice",
            sequence_order=2,
        )
        db.session.add(q1)
        db.session.add(q2)
        db.session.flush()

        wrong1 = QuizQuestionOption(
            question_id=q1.id, option_text="wrong", is_correct=False
        )
        right1 = QuizQuestionOption(
            question_id=q1.id, option_text="right", is_correct=True
        )
        wrong2 = QuizQuestionOption(
            question_id=q2.id, option_text="wrong", is_correct=False
        )
        right2 = QuizQuestionOption(
            question_id=q2.id, option_text="right", is_correct=True
        )
        db.session.add_all([wrong1, right1, wrong2, right2])
        db.session.flush()

        ended = datetime.utcnow() - timedelta(minutes=5)
        session = LearningSession(
            student_id=student.id,
            module_id=mod.id,
            start_time=ended - timedelta(minutes=10),
            end_time=ended,
            is_monitored=True,
            focus_metric_version=FOCUS_METRIC_VERSION,
            observed_focused_seconds=400.0,
            observed_distracted_seconds=50.0,
            unknown_seconds=50.0,
            monitoring_coverage_pct=75.0,
            focus_percentage=88.0,
        )
        db.session.add(session)
        db.session.commit()

        student_id = student.id
        quiz_id = quiz.id
        wrong1_id = wrong1.id
        wrong2_id = wrong2.id
        q1_id = q1.id
        q2_id = q2.id
        doc_id = doc.id
        st_token = create_access_token(
            identity=str(st_user.id), additional_claims={"role": "student"}
        )

    headers = {"Authorization": f"Bearer {st_token}"}
    start = client.post(f"/api/courses/quizzes/{quiz_id}/attempts", headers=headers)
    assert start.status_code == 201
    attempt_id = start.get_json()["attempt_id"]

    submit = client.post(
        f"/api/courses/attempts/{attempt_id}/submit",
        headers=headers,
        json={
            "answers": [
                {"question_id": q1_id, "selected_option_id": wrong1_id},
                {"question_id": q2_id, "selected_option_id": wrong2_id},
            ]
        },
    )
    assert submit.status_code == 200
    body = submit.get_json()
    assert body["score"] == 0.0
    assert body["correct_count"] == 0
    assert body["total_questions"] == 2
    rem = body["remediation"]
    assert rem is not None
    assert rem["error_rate"] == 1.0
    assert rem["reason"] == REASON_COMPREHENSION
    assert rem["path"] == PATH_DIFFERENT
    assert rem["focus_percentage"] == 88.0
    assert rem["monitoring_coverage_pct"] == 75.0
    assert rem["offers"][0]["kind"] == KIND_ALTERNATIVE
    assert rem["offers"][0]["content_id"] == doc_id

    with app.app_context():
        event = db.session.get(RemediationEvent, rem["event_id"])
        assert event is not None
        assert event.student_id == student_id
        assert event.quiz_attempt_id == attempt_id
        assert event.error_rate == 1.0
        assert event.reason == REASON_COMPREHENSION
        assert event.path == PATH_DIFFERENT
        assert event.content_shown["offers"][0]["kind"] == KIND_ALTERNATIVE

    choice = client.post(
        f"/api/courses/remediation/{rem['event_id']}/choice",
        headers=headers,
        json={"choice": KIND_ALTERNATIVE},
    )
    assert choice.status_code == 200
    assert choice.get_json()["student_choice"] == KIND_ALTERNATIVE
