import sys
from pathlib import Path

import bcrypt
import pytest

# Repo root, so tests can import the shared feature code (models.src.features).
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app import create_app
from app.config import Config
from app.extensions import db
from app.db_models import User

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test_jwt_secret"

@pytest.fixture
def app():
    from app.services.ml_service import MLService

    MLService._instance = None
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
    if MLService._instance is not None:
        MLService._instance.shutdown()
    MLService._instance = None


@pytest.fixture(autouse=True)
def _shutdown_ml_after_test():
    """Close MediaPipe session resources so pytest can exit on Windows."""
    yield
    try:
        from app.services.ml_service import MLService

        if MLService._instance is not None:
            MLService._instance.shutdown()
            MLService._instance = None
    except Exception:
        pass

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def admin_user(app):
    hashed = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8")
    user = User(email="admin@test.com", password=hashed, first_name="Admin", last_name="User", role="admin")
    db.session.add(user)
    db.session.commit()
    return user
