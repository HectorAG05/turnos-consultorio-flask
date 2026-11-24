"""API REST en JSON: CRUD de turnos y pacientes y predicción de ausentismo.

| Método | Endpoint                 | Acción                                   |
|--------|--------------------------|------------------------------------------|
| POST   | /api/login               | Iniciar sesión (para Postman)            |
| POST   | /api/logout              | Cerrar sesión                            |
| GET    | /api/turnos              | Listar turnos (filtrados por rol)        |
| GET    | /api/turnos/<id>         | Ver un turno                             |
| POST   | /api/turnos              | Crear turno (CU-01)                      |
| PUT    | /api/turnos/<id>         | Reprogramar: nueva fecha y hora (CU-03)  |
| PATCH  | /api/turnos/<id>         | Registrar asistencia (RF-08)             |
| DELETE | /api/turnos/<id>         | Cancelar turno, baja lógica (CU-04)      |
| GET    | /api/pacientes           | Listar pacientes                         |
| POST   | /api/pacientes           | Crear paciente                           |
| PUT    | /api/pacientes/<dni>     | Modificar paciente                       |
| DELETE | /api/pacientes/<dni>     | Eliminar paciente (si no tiene turnos)   |
| POST   | /api/prediccion          | Predecir ausentismo con el modelo de IA  |

Requiere sesión iniciada (cookie de Flask-Login). Sin sesión responde 401.
"""
from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..ia.servicio import DatosPrediccionInvalidos, nivel_de_riesgo, predecir_ausentismo, validar_datos
from ..models import Medico, Paciente, Turno, Usuario
from ..pacientes.routes import aplicar_datos, validar_paciente
from ..turnos import servicios
from ..turnos.routes import leer_fecha, leer_hora
from ..turnos.servicios import TurnoError

api_bp = Blueprint("api", __name__)


def _json():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        abort(400, description="El cuerpo debe ser un objeto JSON.")
    return datos


def _error(mensaje, codigo):
    return jsonify({"error": mensaje}), codigo


def _solo_secretaria():
    if current_user.rol != "secretaria":
        abort(403)


def _turno_visible(id_turno):
    turno = db.session.get(Turno, id_turno) or abort(404)
    if not servicios.puede_ver(current_user, turno):
        abort(403)
    return turno


def _fecha_y_hora(datos):
    fecha, hora = leer_fecha(datos.get("fecha")), leer_hora(datos.get("hora"))
    if not (fecha and hora):
        abort(400, description="Enviá «fecha» (AAAA-MM-DD) y «hora» (HH:MM).")
    return fecha, hora


# ---------------- Sesión ----------------
@api_bp.post("/login")
def login_api():
    """Login en JSON para probar la API desde Postman. Guarda la sesión en una cookie."""
    datos = _json()
    usuario = Usuario.query.filter_by(username=str(datos.get("username", "")).strip().lower()).first()
    if usuario is None or not usuario.check_password(str(datos.get("password", ""))):
        return _error("Usuario o contraseña incorrectos.", 401)
    login_user(usuario)
    return jsonify({"usuario": usuario.username, "rol": usuario.rol})


@api_bp.post("/logout")
@login_required
def logout_api():
    logout_user()
    return jsonify({"mensaje": "Sesión cerrada."})


# ---------------- Turnos ----------------
@api_bp.get("/turnos")
@login_required
def listar_turnos():
    consulta = servicios.turnos_visibles(current_user)
    fecha = leer_fecha(request.args.get("fecha"))
    if fecha:
        consulta = consulta.filter(Turno.fecha == fecha)
    turnos = consulta.order_by(Turno.fecha, Turno.hora).all()
    return jsonify([t.to_dict() for t in turnos])


@api_bp.get("/turnos/<int:id_turno>")
@login_required
def ver_turno(id_turno):
    return jsonify(_turno_visible(id_turno).to_dict())


@api_bp.post("/turnos")
@login_required
def crear_turno():
    if current_user.rol not in ("secretaria", "paciente"):
        abort(403)
    datos = _json()
    dni = current_user.dni if current_user.rol == "paciente" else str(datos.get("dni_paciente", ""))
    paciente = db.session.get(Paciente, dni)
    medico = db.session.get(Medico, str(datos.get("matricula_medico", "")))
    if paciente is None or medico is None:
        return _error("Paciente o médico inexistente.", 404)
    fecha, hora = _fecha_y_hora(datos)
    try:
        turno = servicios.crear_turno(paciente, medico, fecha, hora)
    except TurnoError as error:
        return _error(str(error), 409)
    return jsonify(turno.to_dict()), 201


@api_bp.put("/turnos/<int:id_turno>")
@login_required
def reprogramar_turno(id_turno):
    turno = _turno_visible(id_turno)
    if not servicios.puede_modificar(current_user, turno):
        abort(403)
    fecha, hora = _fecha_y_hora(_json())
    try:
        servicios.reprogramar_turno(turno, fecha, hora, current_user.rol)
    except TurnoError as error:
        return _error(str(error), 409)
    return jsonify(turno.to_dict())


@api_bp.patch("/turnos/<int:id_turno>")
@login_required
def actualizar_estado_turno(id_turno):
    turno = _turno_visible(id_turno)
    if current_user.rol not in ("secretaria", "medico"):
        abort(403)
    try:
        servicios.registrar_asistencia(turno, _json().get("estado", ""))
    except TurnoError as error:
        return _error(str(error), 409)
    return jsonify(turno.to_dict())


@api_bp.delete("/turnos/<int:id_turno>")
@login_required
def cancelar_turno(id_turno):
    turno = _turno_visible(id_turno)
    if not servicios.puede_modificar(current_user, turno):
        abort(403)
    try:
        servicios.cancelar_turno(turno)
    except TurnoError as error:
        return _error(str(error), 409)
    return jsonify(turno.to_dict())


# ---------------- Pacientes ----------------
@api_bp.get("/pacientes")
@login_required
def listar_pacientes():
    _solo_secretaria()
    return jsonify([p.to_dict() for p in Paciente.query.order_by(Paciente.apellido).all()])


@api_bp.post("/pacientes")
@login_required
def crear_paciente():
    _solo_secretaria()
    datos = {k: str(v) if v is not None else "" for k, v in _json().items()}
    errores = validar_paciente(datos, es_alta=True)
    if errores:
        return jsonify({"errores": errores}), 400
    paciente = Paciente(dni=datos["dni"])
    aplicar_datos(paciente, datos)
    db.session.add(paciente)
    db.session.commit()
    return jsonify(paciente.to_dict()), 201


@api_bp.put("/pacientes/<dni>")
@login_required
def modificar_paciente(dni):
    _solo_secretaria()
    paciente = db.session.get(Paciente, dni) or abort(404)
    datos = {k: str(v) if v is not None else "" for k, v in _json().items()}
    errores = validar_paciente(datos, es_alta=False)
    if errores:
        return jsonify({"errores": errores}), 400
    aplicar_datos(paciente, datos)
    db.session.commit()
    return jsonify(paciente.to_dict())


@api_bp.delete("/pacientes/<dni>")
@login_required
def eliminar_paciente(dni):
    _solo_secretaria()
    paciente = db.session.get(Paciente, dni) or abort(404)
    if Turno.query.filter_by(dni_paciente=dni).count():
        return _error("El paciente tiene turnos en su historial y no se puede eliminar.", 409)
    Usuario.query.filter_by(dni=dni).delete()
    db.session.delete(paciente)
    db.session.commit()
    return "", 204


# ---------------- IA ----------------
@api_bp.post("/prediccion")
@login_required
def prediccion():
    try:
        datos = validar_datos(_json())
        probabilidad = predecir_ausentismo(datos)
    except DatosPrediccionInvalidos as error:
        return _error(str(error), 400)
    except RuntimeError as error:
        return _error(str(error), 503)
    return jsonify(
        {
            "entrada": datos,
            "probabilidad_ausentismo": round(probabilidad, 4),
            "nivel_de_riesgo": nivel_de_riesgo(probabilidad),
        }
    )
