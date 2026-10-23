import bcrypt
import pytest
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
    MLService._instance = None

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
