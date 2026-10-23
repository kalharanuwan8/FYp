"""
Flask configuration. Values are read from environment variables, which
should be set via backend/.env (see .env.example for required keys).
python-dotenv loads .env automatically when create_app() calls load_dotenv()
in app/__init__.py, before this class is instantiated.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Core Flask ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # --- Database ---
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///adhd_lms.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- JWT (flask-jwt-extended) ---
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)  # NFR-SEC-04: session expiry

    # --- File uploads (FR-TCH-03) ---
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", 500)) * 1024 * 1024
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")

    # --- ML inference service (services/ml_service.py) ---
    ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://localhost:8001")

    # --- LLM (Ollama) for material summary + milestone quiz pack ---
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434")
    LLM_MODEL = os.environ.get("LLM_MODEL", "llama3.1:latest")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}