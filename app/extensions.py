"""Extensiones de Flask creadas una sola vez y conectadas a la app en create_app()."""
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
