from datetime import time

import pytest

from app.extensions import db
from app.models import Medico, Paciente, Turno
from app.turnos import servicios
from app.turnos.servicios import TurnoError

from .conftest import proximo


@pytest.fixture
def datos(app):
    with app.app_context():
        yield {
            "gomez": db.session.get(Medico, "MN-1001"),  # lunes a viernes de 09:00 a 12:00
            "lucia": db.session.get(Paciente, "32456789"),
            "maria": db.session.get(Paciente, "30111222"),
        }


def test_horarios_disponibles_respetan_la_agenda_del_medico(datos):
    lunes = proximo(0)
    horarios = servicios.horarios_disponibles(datos["gomez"], lunes)
    assert time(9, 0) in horarios and time(11, 30) in horarios
    assert time(12, 0) not in horarios  # termina a las 12:00
    assert servicios.horarios_disponibles(datos["gomez"], proximo(6)) == []  # domingo no atiende


def test_crear_turno_ocupa_el_horario(datos):
    lunes = proximo(0)
    turno = servicios.crear_turno(datos["lucia"], datos["gomez"], lunes, time(9, 0))
    assert turno.estado == "confirmado"
    assert time(9, 0) not in servicios.horarios_disponibles(datos["gomez"], lunes)


def test_no_se_superponen_turnos(datos):
    lunes = proximo(0)
    servicios.crear_turno(datos["lucia"], datos["gomez"], lunes, time(9, 30))
    with pytest.raises(TurnoError):
        servicios.crear_turno(datos["maria"], datos["gomez"], lunes, time(9, 30))


def test_no_se_dan_turnos_fuera_del_horario_de_atencion(datos):
    with pytest.raises(TurnoError):
        servicios.crear_turno(datos["lucia"], datos["gomez"], proximo(0), time(15, 0))


def test_reprogramar_cambia_estado_y_libera_el_horario_anterior(datos):
    lunes, martes = proximo(0), proximo(1)
    turno = servicios.crear_turno(datos["lucia"], datos["gomez"], lunes, time(10, 0))
    servicios.reprogramar_turno(turno, martes, time(11, 0), "secretaria")
    assert turno.estado == "reprogramado"
    assert time(10, 0) in servicios.horarios_disponibles(datos["gomez"], lunes)


def test_cancelar_es_baja_logica_y_libera_el_horario(datos):
    lunes = proximo(0)
    turno = servicios.crear_turno(datos["lucia"], datos["gomez"], lunes, time(10, 30))
    servicios.cancelar_turno(turno)
    assert db.session.get(Turno, turno.id_turno).estado == "cancelado"  # no se borró
    assert time(10, 30) in servicios.horarios_disponibles(datos["gomez"], lunes)
    # El horario liberado se puede volver a dar
    servicios.crear_turno(datos["maria"], datos["gomez"], lunes, time(10, 30))


def test_flujo_completo_desde_las_pantallas(secretaria, app):
    lunes = proximo(0)
    respuesta = secretaria.post(
        "/turnos/nuevo",
        data={"dni": "30111222", "matricula": "MN-1001", "fecha": lunes.isoformat(), "hora": "11:00"},
        follow_redirects=True,
    )
    assert "Turno confirmado" in respuesta.get_data(as_text=True)
    with app.app_context():
        turno = Turno.query.filter_by(fecha=lunes, hora=time(11, 0), matricula_medico="MN-1001").first()
        assert turno is not None
        id_turno = turno.id_turno

    secretaria.post(f"/turnos/{id_turno}/cancelar")
    with app.app_context():
        assert db.session.get(Turno, id_turno).estado == "cancelado"


def test_paciente_solo_ve_sus_turnos(paciente):
    texto = paciente.get("/turnos/").get_data(as_text=True)
    assert "Mis turnos" in texto
    assert "Carlos Díaz" not in texto


def test_crud_de_pacientes(secretaria, app):
    secretaria.post(
        "/pacientes/nuevo",
        data={"dni": "41222333", "nombre": "Tomás", "apellido": "Vega", "telefono": "11 4000-1111"},
    )
    secretaria.post(
        "/pacientes/41222333/editar",
        data={"nombre": "Tomás", "apellido": "Vega Paz", "telefono": "11 4000-2222"},
    )
    with app.app_context():
        assert db.session.get(Paciente, "41222333").apellido == "Vega Paz"
    secretaria.post("/pacientes/41222333/eliminar")
    with app.app_context():
        assert db.session.get(Paciente, "41222333") is None


def test_no_se_elimina_un_paciente_con_turnos(secretaria, app):
    secretaria.post("/pacientes/28333444/eliminar")
    with app.app_context():
        assert db.session.get(Paciente, "28333444") is not None
