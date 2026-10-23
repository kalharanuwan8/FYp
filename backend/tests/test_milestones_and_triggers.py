"""Tests for LLM material pack, manual intervention trigger, and milestone grading."""
from unittest.mock import patch

import pytest
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
    GuardianConsent,
    LearningSession,
    InterventionLog,
    MilestoneQuestion,
)
from app.extensions import db
from app.services.llm_service import LLMService


def _teacher_headers(app):
    with app.app_context():
        gl = GradeLevel(name="Grade AI")
        db.session.add(gl)
        u = User(
            email="teacher_llm@test.com",
            password="hash",
            role="teacher",
            first_name="T",
            last_name="L",
        )
        db.session.add(u)
        db.session.flush()
        teacher = Teacher(user_id=u.id)
        db.session.add(teacher)
        db.session.flush()
        subj = Subject(title="AI Course", description="d", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subj.id))
        mod = Module(subject_id=subj.id, title="M1", sequence_order=1)
        db.session.add(mod)
        db.session.commit()
        token = create_access_token(identity=str(u.id), additional_claims={"role": "teacher"})
        return {"Authorization": f"Bearer {token}"}, mod.id


def _student_session(app, with_milestones=True):
    with app.app_context():
        gl = GradeLevel.query.filter_by(name="Grade AI").first() or GradeLevel(name="Grade AI2")
        if not gl.id:
            db.session.add(gl)
            db.session.flush()

        t_user = User(
            email="teacher_ms@test.com",
            password="hash",
            role="teacher",
            first_name="T",
            last_name="M",
        )
        db.session.add(t_user)
        db.session.flush()
        teacher = Teacher(user_id=t_user.id)
        db.session.add(teacher)
        db.session.flush()

        subj = Subject(title="MS Course", description="d", grade_level_id=gl.id)
        db.session.add(subj)
        db.session.flush()
        db.session.add(TeacherSubject(teacher_id=teacher.id, subject_id=subj.id))
        mod = Module(subject_id=subj.id, title="Module MS", sequence_order=1)
        db.session.add(mod)
        db.session.flush()

        content = ModuleContent(
            module_id=mod.id,
            content_type="document",
            title="Notes",
            summary="Photosynthesis converts light to energy.",
        )
        db.session.add(content)
        db.session.flush()

        if with_milestones:
            db.session.add(
                ModuleMilestoneItem(
                    module_content_id=content.id,
                    question="What does photosynthesis convert?",
                    options_json=["Light to energy", "Water to gold", "Sound to heat", "None"],
                    correct_option=0,
                    hint_text="Think about plants and sunlight.",
                    sequence_order=1,
                )
            )

        s_user = User(
            email="student_ms@test.com",
            password="hash",
            role="student",
            first_name="S",
            last_name="M",
        )
        db.session.add(s_user)
        db.session.flush()
        student = Student(user_id=s_user.id)
        db.session.add(student)
        db.session.flush()
        db.session.add(Enrollment(student_id=student.id, subject_id=subj.id))
        db.session.add(
            GuardianConsent(
                student_id=student.id,
                guardian_name="Parent",
                guardian_email="parent@test.com",
                consent_given=True,
            )
        )
        db.session.commit()

        token = create_access_token(
            identity=str(s_user.id), additional_claims={"role": "student"}
        )
        return {
            "headers": {"Authorization": f"Bearer {token}"},
            "module_id": mod.id,
            "content_id": content.id,
        }


def test_llm_service_parses_json_pack():
    svc = LLMService()
    raw = (
        '{"summary":"A short summary.","milestones":['
        '{"question":"Q1?","options":["A","B","C","D"],"correct_option":1,"hint":"h"}]}'
    )
    with patch.object(LLMService, "_chat", return_value=raw):
        pack = svc.generate_material_pack("Teacher notes about cells.")
    assert "summary" in pack
    assert pack["summary"] == "A short summary."
    assert len(pack["milestones"]) == 1
    assert pack["milestones"][0]["correct_option"] == 1


def test_generate_pack_endpoint_mocked(client, app):
    headers, _mod_id = _teacher_headers(app)
    fake = {
        "summary": "Generated summary",
        "milestones": [
            {
                "question": "Main idea?",
                "options": ["X", "Y", "Z", "W"],
                "correct_option": 0,
                "hint_text": "hint",
                "sequence_order": 1,
            }
        ],
    }
    with patch(
        "app.routes.courses.LLMService.generate_material_pack", return_value=fake
    ):
        res = client.post(
            "/api/courses/materials/generate-pack",
            json={"description": "Long teacher notes about fractions.", "title": "Fractions"},
            headers=headers,
        )
    assert res.status_code == 200
    assert res.json["summary"] == "Generated summary"
    assert len(res.json["milestones"]) == 1


def test_create_material_with_milestones(client, app):
    headers, mod_id = _teacher_headers(app)
    payload = {
        "title": "Lecture notes",
        "content_type": "document",
        "summary": "Edited summary",
        "milestones": [
            {
                "question": "What is 2+2?",
                "options": ["3", "4", "5", "6"],
                "correct_option": 1,
                "hint_text": "Basic arithmetic",
            }
        ],
    }
    res = client.post(
        f"/api/courses/modules/{mod_id}/materials",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json["summary"] == "Edited summary"
    assert len(res.json["milestones"]) == 1
    assert res.json["milestones"][0]["correct_option"] == 1

    with app.app_context():
        items = ModuleMilestoneItem.query.filter_by(
            module_content_id=res.json["id"]
        ).all()
        assert len(items) == 1


def test_manual_trigger_and_milestone_grading(client, app):
    # ensure grade level exists for helper
    with app.app_context():
        if not GradeLevel.query.filter_by(name="Grade AI").first():
            db.session.add(GradeLevel(name="Grade AI"))
            db.session.commit()

    ctx = _student_session(app, with_milestones=True)
    headers = ctx["headers"]

    start = client.post(
        "/api/session/start",
        json={"module_id": ctx["module_id"], "is_monitored": True},
        headers=headers,
    )
    assert start.status_code == 201
    session_id = start.json["session_id"]

    trig = client.post(
        f"/api/session/{session_id}/trigger-intervention",
        json={"tier": 3, "is_quiz_context": False},
        headers=headers,
    )
    assert trig.status_code == 200
    assert trig.json["intervention_triggered"] is True
    intervention = trig.json["intervention"]
    assert intervention["intervention_type"] == "milestone_quiz"
    assert "options" in intervention["payload"]
    iid = intervention["intervention_id"]
    item_id = intervention["payload"].get("milestone_item_id")

    # Pending blocks second trigger
    trig2 = client.post(
        f"/api/session/{session_id}/trigger-intervention",
        json={"tier": 1},
        headers=headers,
    )
    assert trig2.status_code == 409

    resp = client.post(
        f"/api/session/{session_id}/intervention-response",
        json={
            "intervention_id": iid,
            "user_response": "reengaged",
            "student_answer": "Light to energy",
            "selected_option": 0,
            "milestone_item_id": item_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json["is_correct"] is True

    with app.app_context():
        mq = MilestoneQuestion.query.filter_by(intervention_id=iid).first()
        assert mq is not None
        assert mq.student_answer == "Light to energy"
        assert mq.is_correct is True
