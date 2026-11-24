from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.utils import hoy
from config import TestingConfig

PASSWORD = TestingConfig.SEED_PASSWORD


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password=PASSWORD):
    return client.post("/auth/login", data={"username": username, "password": password})


@pytest.fixture
def secretaria(client):
    login(client, "laura")
    return client


@pytest.fixture
def paciente(client):
    login(client, "lucia")
    return client


def proximo(dia_semana, semanas=2):
    """Fecha futura que cae en el día indicado (0 = lunes), a varias semanas de hoy."""
    base = hoy() + timedelta(weeks=semanas)
    return base + timedelta(days=(dia_semana - base.weekday()) % 7)
