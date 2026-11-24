"""Configuración de la aplicación.

Todos los datos sensibles se leen de variables de entorno (archivo .env en
desarrollo, variables del servicio en Render). Nunca se escriben en el código.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _database_url():
    """SQLite en desarrollo; PostgreSQL en producción (variable DATABASE_URL)."""
    url = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'instance' / 'turnos.db'}"
    # Render entrega la URL con el esquema "postgres://", pero SQLAlchemy exige "postgresql://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    MODEL_PATH = os.getenv("MODEL_PATH", str(BASE_DIR / "models" / "modelo_ausentismo.joblib"))
    # Contraseña de los usuarios de demostración que se crean la primera vez
    SEED_PASSWORD = os.getenv("SEED_PASSWORD")

    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "clave-solo-para-tests"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SEED_PASSWORD = "demo1234"
    CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
