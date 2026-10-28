"""One-shot prep for manual remediation screenshot. Delete after use."""
from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    contents = db.session.execute(
        text(
            """
        SELECT id, content_type, title, LEFT(COALESCE(summary,''),80) AS summary_preview,
               (SELECT COUNT(*) FROM module_milestone_items mi
                WHERE mi.module_content_id = mc.id AND mi.is_active) AS active_ms
        FROM module_contents mc WHERE module_id = 2 ORDER BY id
    """
        )
    ).mappings().all()
    print("CONTENTS:")
    for r in contents:
        print(dict(r))

    attempts = db.session.execute(
        text(
            """
        SELECT qa.id, qa.quiz_id, qa.student_id, qa.score, qa.completed_at, u.email
        FROM quiz_attempts qa
        JOIN students st ON st.id = qa.student_id
        JOIN users u ON u.id = st.user_id
        WHERE qa.quiz_id = 1
        ORDER BY qa.id
    """
        )
    ).mappings().all()
    print("QUIZ1_ATTEMPTS:")
    for r in attempts:
        print(dict(r))

    exists = db.session.execute(
        text("SELECT 1 FROM enrollments WHERE student_id=6 AND subject_id=3")
    ).first()
    print("ENROLL_EXISTS", bool(exists))
    if not exists:
        db.session.execute(
            text("INSERT INTO enrollments (student_id, subject_id) VALUES (6, 3)")
        )
        db.session.commit()
        print("ENROLLED student_id=6 subject_id=3")

    qs = db.session.execute(
        text(
            """
        SELECT qq.id, qq.question_text, qo.id AS opt_id, qo.option_text, qo.is_correct
        FROM quiz_questions qq
        LEFT JOIN quiz_question_options qo ON qo.question_id = qq.id
        WHERE qq.quiz_id = 1 ORDER BY qq.id, qo.id
    """
        )
    ).mappings().all()
    print("QUESTIONS:")
    for r in qs:
        print(dict(r))

    tables = db.session.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "AND tablename='remediation_events'"
        )
    ).first()
    print("REMEDIATION_TABLE", bool(tables))
