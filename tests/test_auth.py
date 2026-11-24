from app.models import Usuario

from .conftest import PASSWORD, login


def test_las_contrasenas_se_guardan_hasheadas_con_bcrypt(app):
    with app.app_context():
        usuario = Usuario.query.filter_by(username="laura").first()
        assert usuario.password_hash != PASSWORD
        assert usuario.password_hash.startswith("$2b$")
        assert usuario.check_password(PASSWORD)
        assert not usuario.check_password("otra-clave")


def test_login_correcto_y_logout(client):
    respuesta = login(client, "laura")
    assert respuesta.status_code == 302
    assert client.get("/turnos/").status_code == 200
    client.post("/auth/logout")
    assert client.get("/turnos/").status_code == 302  # vuelve a pedir login


def test_login_con_contrasena_incorrecta(client):
    respuesta = login(client, "laura", "incorrecta")
    assert respuesta.status_code == 401
    assert "incorrectos" in respuesta.get_data(as_text=True)


def test_rutas_protegidas_redirigen_al_login(client):
    respuesta = client.get("/pacientes/")
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_paciente_no_accede_a_pacientes(paciente):
    assert paciente.get("/pacientes/").status_code == 403


def test_registro_de_paciente(client, app):
    respuesta = client.post(
        "/auth/registro",
        data={
            "dni": "40123456",
            "nombre": "Sofía",
            "apellido": "Martínez",
            "telefono": "11 5000-0000",
            "username": "sofia",
            "password": "claveSegura1",
            "password2": "claveSegura1",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        usuario = Usuario.query.filter_by(username="sofia").first()
        assert usuario.rol == "paciente" and usuario.paciente.apellido == "Martínez"
