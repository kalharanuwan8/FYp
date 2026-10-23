"""
App Factory. wsgi.py imports create_app() from here to actually launch
the server (via `flask run`, gunicorn, or eventlet directly for SocketIO).
"""

import os
import traceback
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from app.config import config_by_name
from app.extensions import db, migrate, jwt, socketio


def create_app(env=None):
    load_dotenv()  # reads backend/.env

    env = env or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name[env])

    # Allowed CORS Origins from environment (comma separated)
    raw_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    # --- Bind shared extensions to this app instance ---
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app, resources={r"/*": {"origins": allowed_origins}}, supports_credentials=True)
    socketio.init_app(app, cors_allowed_origins=allowed_origins)

    # --- Register SocketIO Telemetry Event Listeners ---
    from app.socket_events.telemetry import init_telemetry_events
    init_telemetry_events()

    # --- Global Exception Handler & CORS Header Guarantee ---
    @app.after_request
    def after_request(response):
        origin = response.headers.get("Access-Control-Allow-Origin")
        if not origin:
            response.headers["Access-Control-Allow-Origin"] = allowed_origins[0] if allowed_origins else "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,PATCH,OPTIONS"
        return response

    @app.errorhandler(Exception)
    def handle_exception(e):
        traceback.print_exc()
        is_debug = app.config.get("DEBUG", False) or app.config.get("TESTING", False)
        payload = {"error": "Internal Server Error"}
        if is_debug:
            payload["details"] = str(e)

        response = jsonify(payload)
        response.status_code = 500
        return response

    # --- Import models & Ensure all DB tables exist ---
    from app.db_models import user, course, quiz, session, analytics, system_setting, gamification  # noqa: F401
    from app.db_models.system_setting import SystemSetting

    with app.app_context():
        db.create_all()
        # Lightweight schema patches (SQLite alters + Postgres session FK retarget)
        try:
            from sqlalchemy import text, inspect
            insp = inspect(db.engine)
            tables = insp.get_table_names()
            dialect = db.engine.dialect.name

            if "students" in tables:
                student_cols = {c["name"] for c in insp.get_columns("students")}
                # Postgres needs FALSE; SQLite accepts 0
                bool_false = "FALSE" if dialect == "postgresql" else "0"
                json_type = "JSONB" if dialect == "postgresql" else "JSON"
                if "ui_preferences" not in student_cols:
                    db.session.execute(
                        text(f"ALTER TABLE students ADD COLUMN ui_preferences {json_type}")
                    )
                if "student_assent" not in student_cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE students ADD COLUMN student_assent "
                            f"BOOLEAN DEFAULT {bool_false}"
                        )
                    )
                if "onboarding_completed" not in student_cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE students ADD COLUMN onboarding_completed "
                            f"BOOLEAN DEFAULT {bool_false}"
                        )
                    )
                db.session.commit()

            if "intervention_logs" in tables:
                cols = {c["name"] for c in insp.get_columns("intervention_logs")}
                if "distraction_event_id" not in cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE intervention_logs "
                            "ADD COLUMN distraction_event_id INTEGER"
                        )
                    )
                    db.session.commit()
                if "noise_action" not in cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE intervention_logs "
                            "ADD COLUMN noise_action VARCHAR(50)"
                        )
                    )
                    db.session.commit()
            if "milestone_questions" in tables:
                mq_cols = {c["name"] for c in insp.get_columns("milestone_questions")}
                if "milestone_item_id" not in mq_cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE milestone_questions "
                            "ADD COLUMN milestone_item_id INTEGER"
                        )
                    )
                if "correct_option" not in mq_cols:
                    db.session.execute(
                        text(
                            "ALTER TABLE milestone_questions "
                            "ADD COLUMN correct_option INTEGER"
                        )
                    )
                db.session.commit()

            # sessions.module_content_id historically FKd to module_contents, but the
            # app stores Module.id there. Retarget the Postgres FK to modules(id).
            if dialect == "postgresql" and "sessions" in tables:
                fks = insp.get_foreign_keys("sessions")
                needs_retarget = False
                for fk in fks:
                    if (
                        fk.get("constrained_columns") == ["module_content_id"]
                        and fk.get("referred_table") == "module_contents"
                    ):
                        needs_retarget = True
                        fk_name = fk.get("name") or "sessions_module_content_id_fkey"
                        db.session.execute(
                            text(f'ALTER TABLE sessions DROP CONSTRAINT IF EXISTS "{fk_name}"')
                        )
                if needs_retarget:
                    # Remap any rows that still point at a ModuleContent id
                    db.session.execute(
                        text(
                            """
                            UPDATE sessions AS s
                            SET module_content_id = mc.module_id
                            FROM module_contents AS mc
                            WHERE s.module_content_id = mc.id
                              AND NOT EXISTS (
                                  SELECT 1 FROM modules m WHERE m.id = s.module_content_id
                              )
                            """
                        )
                    )
                    db.session.execute(
                        text(
                            """
                            ALTER TABLE sessions
                            ADD CONSTRAINT sessions_module_content_id_fkey
                            FOREIGN KEY (module_content_id) REFERENCES modules(id)
                            """
                        )
                    )
                    db.session.commit()

            # milestone_questions.intervention_id historically FKd to interventions,
            # but the app stores InterventionLog in intervention_logs. Retarget FK.
            if dialect == "postgresql" and "milestone_questions" in tables:
                fks = insp.get_foreign_keys("milestone_questions")
                needs_retarget = False
                for fk in fks:
                    if (
                        fk.get("constrained_columns") == ["intervention_id"]
                        and fk.get("referred_table") == "interventions"
                    ):
                        needs_retarget = True
                        fk_name = fk.get("name") or "milestone_questions_intervention_id_fkey"
                        db.session.execute(
                            text(f'ALTER TABLE milestone_questions DROP CONSTRAINT IF EXISTS "{fk_name}"')
                        )
                if needs_retarget:
                    db.session.execute(
                        text(
                            """
                            DELETE FROM milestone_questions
                            WHERE intervention_id NOT IN (SELECT id FROM intervention_logs)
                            """
                        )
                    )
                    db.session.execute(
                        text(
                            """
                            ALTER TABLE milestone_questions
                            ADD CONSTRAINT milestone_questions_intervention_id_fkey
                            FOREIGN KEY (intervention_id) REFERENCES intervention_logs(id)
                            """
                        )
                    )
                    db.session.commit()
        except Exception:
            db.session.rollback()
            traceback.print_exc()

        # Seed default system settings if missing
        defaults = {
            "intervention_min_cooldown_seconds": "30",
            "intervention_max_cooldown_seconds": "120",
            "data_retention_days": "90",
        }
        for k, v in defaults.items():
            if not db.session.get(SystemSetting, k):
                db.session.add(SystemSetting(key=k, value=v))
        db.session.commit()

    # --- Serve Uploaded Material Files ---
    @app.route("/uploads/<filename>")
    def serve_upload(filename):
        uploads_dir = os.path.join(app.root_path, "..", "uploads")
        return send_from_directory(uploads_dir, filename)

    # --- Register blueprints ---
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.courses import courses_bp
    from app.routes.quizzes import quizzes_bp
    from app.routes.session import session_bp
    from app.routes.analytics import analytics_bp
    from app.routes.student_profile import student_profile_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(courses_bp, url_prefix="/api/courses")
    app.register_blueprint(quizzes_bp, url_prefix="/api/courses")
    app.register_blueprint(session_bp, url_prefix="/api/session")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(student_profile_bp, url_prefix="/api/student")

    return app