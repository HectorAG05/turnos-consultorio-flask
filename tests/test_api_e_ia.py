from app.ia.servicio import nivel_de_riesgo, predecir_ausentismo

from .conftest import PASSWORD, proximo


def test_login_y_logout_por_api(client):
    assert client.post("/api/login", json={"username": "laura", "password": "mala"}).status_code == 401
    respuesta = client.post("/api/login", json={"username": "laura", "password": PASSWORD})
    assert respuesta.get_json() == {"usuario": "laura", "rol": "secretaria"}
    assert client.get("/api/turnos").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/turnos").status_code == 401


def test_api_sin_sesion_responde_401(client):
    respuesta = client.get("/api/turnos")
    assert respuesta.status_code == 401
    assert "error" in respuesta.get_json()


def test_crud_de_turnos_por_api(secretaria):
    lunes, martes = proximo(0, semanas=3), proximo(1, semanas=3)

    # POST: crear
    creado = secretaria.post(
        "/api/turnos",
        json={"dni_paciente": "35555666", "matricula_medico": "MN-1001", "fecha": lunes.isoformat(), "hora": "09:00"},
    )
    assert creado.status_code == 201
    id_turno = creado.get_json()["id_turno"]

    # GET: leer
    assert secretaria.get(f"/api/turnos/{id_turno}").get_json()["estado"] == "confirmado"
    assert any(t["id_turno"] == id_turno for t in secretaria.get("/api/turnos").get_json())

    # PUT: reprogramar
    reprogramado = secretaria.put(f"/api/turnos/{id_turno}", json={"fecha": martes.isoformat(), "hora": "10:00"})
    assert reprogramado.status_code == 200
    assert reprogramado.get_json()["estado"] == "reprogramado"

    # DELETE: cancelar (baja lógica)
    cancelado = secretaria.delete(f"/api/turnos/{id_turno}")
    assert cancelado.get_json()["estado"] == "cancelado"
    assert secretaria.delete(f"/api/turnos/{id_turno}").status_code == 409


def test_patch_registra_asistencia(secretaria):
    creado = secretaria.post(
        "/api/turnos",
        json={"dni_paciente": "27777888", "matricula_medico": "MN-1001", "fecha": proximo(2, 3).isoformat(), "hora": "11:00"},
    ).get_json()
    respuesta = secretaria.patch(f"/api/turnos/{creado['id_turno']}", json={"estado": "atendido"})
    assert respuesta.get_json()["estado"] == "atendido"


def test_api_rechaza_horario_ocupado(secretaria):
    datos = {"dni_paciente": "30111222", "matricula_medico": "MN-1001", "fecha": proximo(3, 3).isoformat(), "hora": "09:30"}
    assert secretaria.post("/api/turnos", json=datos).status_code == 201
    datos["dni_paciente"] = "35555666"
    assert secretaria.post("/api/turnos", json=datos).status_code == 409


def test_crud_de_pacientes_por_api(secretaria):
    nuevo = {"dni": "42333444", "nombre": "Bruno", "apellido": "Sosa", "telefono": "11 4111-2222"}
    assert secretaria.post("/api/pacientes", json=nuevo).status_code == 201
    modificado = secretaria.put("/api/pacientes/42333444", json={**nuevo, "telefono": "11 4999-0000"})
    assert modificado.get_json()["telefono"] == "11 4999-0000"
    assert secretaria.delete("/api/pacientes/42333444").status_code == 204


def test_el_modelo_se_carga_al_iniciar(app):
    paquete = app.extensions["modelo_ausentismo"]
    assert paquete is not None
    assert paquete["features"] == ["dias_anticipacion", "hora", "tiene_obra_social", "ausencias_previas"]


def test_prediccion_devuelve_una_probabilidad(app):
    with app.app_context():
        bajo = predecir_ausentismo({"dias_anticipacion": 1, "hora": 9, "tiene_obra_social": 1, "ausencias_previas": 0})
        alto = predecir_ausentismo({"dias_anticipacion": 50, "hora": 19, "tiene_obra_social": 0, "ausencias_previas": 4})
    assert 0 <= bajo <= 1 and 0 <= alto <= 1
    assert alto > bajo
    assert nivel_de_riesgo(alto) == "alto"


def test_api_de_prediccion(secretaria):
    respuesta = secretaria.post(
        "/api/prediccion",
        json={"dias_anticipacion": 30, "hora": 18, "tiene_obra_social": 0, "ausencias_previas": 2},
    )
    cuerpo = respuesta.get_json()
    assert respuesta.status_code == 200
    assert 0 <= cuerpo["probabilidad_ausentismo"] <= 1
    assert secretaria.post("/api/prediccion", json={"hora": 99}).status_code == 400
