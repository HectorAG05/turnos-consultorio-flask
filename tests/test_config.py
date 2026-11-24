from sqlalchemy import create_engine

from config import normalizar_url_postgres


def test_url_de_render_usa_el_driver_psycopg2():
    for url in ("postgres://u:p@host:5432/turnos", "postgresql://u:p@host:5432/turnos"):
        normalizada = normalizar_url_postgres(url)
        assert normalizada == "postgresql+psycopg2://u:p@host:5432/turnos"
        # create_engine no se conecta: solo verifica que el driver esté instalado
        assert create_engine(normalizada).dialect.driver == "psycopg2"


def test_sqlite_no_se_modifica():
    assert normalizar_url_postgres("sqlite:///instance/turnos.db") == "sqlite:///instance/turnos.db"
