"""Blueprint de turnos: el CRUD principal del SRS (CU-01 a CU-04) en pantallas HTML."""
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..auth.decoradores import roles_requeridos
from ..extensions import db
from ..ia.servicio import nivel_de_riesgo, riesgo_de_turno
from ..models import Especialidad, Medico, Paciente, Turno
from ..utils import hoy
from . import servicios
from .servicios import TurnoError

turnos_bp = Blueprint("turnos", __name__)

MAX_TURNOS_PACIENTE = 20  # DF-08: como máximo los 20 turnos más recientes


def leer_fecha(texto):
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def leer_hora(texto):
    try:
        return datetime.strptime(texto, "%H:%M").time() if texto else None
    except ValueError:
        return None


def _obtener_turno_visible(id_turno):
    turno = db.session.get(Turno, id_turno) or abort(404)
    if not servicios.puede_ver(current_user, turno):
        abort(403)
    return turno


# ---------- CU-02 Consultar turnos (Read) ----------
@turnos_bp.route("/")
@login_required
def agenda():
    consulta = servicios.turnos_visibles(current_user)
    fecha = None
    matricula = request.args.get("matricula", "")

    if current_user.rol == "paciente":
        turnos = consulta.order_by(Turno.fecha.desc(), Turno.hora.desc()).limit(MAX_TURNOS_PACIENTE).all()
    else:
        fecha = leer_fecha(request.args.get("fecha")) or hoy()
        consulta = consulta.filter(Turno.fecha == fecha)
        if current_user.rol == "secretaria" and matricula:
            consulta = consulta.filter(Turno.matricula_medico == matricula)
        turnos = consulta.order_by(Turno.hora).all()

    # IA: probabilidad de ausentismo de cada turno activo (solo para el personal)
    riesgos = {}
    if current_user.rol in ("secretaria", "medico"):
        for turno in turnos:
            if turno.esta_activo:
                probabilidad = riesgo_de_turno(turno)
                if probabilidad is not None:
                    riesgos[turno.id_turno] = (probabilidad, nivel_de_riesgo(probabilidad))

    return render_template(
        "turnos/agenda.html",
        turnos=turnos,
        fecha=fecha,
        dia_anterior=fecha - timedelta(days=1) if fecha else None,
        dia_siguiente=fecha + timedelta(days=1) if fecha else None,
        medicos=Medico.query.order_by(Medico.apellido).all(),
        matricula=matricula,
        riesgos=riesgos,
    )


@turnos_bp.route("/<int:id_turno>")
@login_required
def detalle(id_turno):
    turno = _obtener_turno_visible(id_turno)
    probabilidad = riesgo_de_turno(turno) if current_user.rol != "paciente" and turno.esta_activo else None
    return render_template(
        "turnos/detalle.html",
        turno=turno,
        probabilidad=probabilidad,
        nivel=nivel_de_riesgo(probabilidad) if probabilidad is not None else None,
    )


# ---------- CU-01 Agendar turno (Create) ----------
@turnos_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@roles_requeridos("secretaria", "paciente")
def nuevo():
    if request.method == "POST":
        return _crear_desde_formulario()

    # Paso 1: paciente (la secretaria ingresa el DNI; el paciente usa el de su sesión)
    paciente = None
    dni = request.args.get("dni", "").strip()
    if current_user.rol == "paciente":
        paciente = current_user.paciente
    elif dni:
        paciente = db.session.get(Paciente, dni)
        if paciente is None:
            # CU-01 flujo alternativo 1a: el DNI no está registrado
            flash("Ese DNI no está registrado. Podés darlo de alta y volver a pedir el turno.", "aviso")

    # Paso 2: especialidad, médico y fecha
    especialidades = Especialidad.query.order_by(Especialidad.nombre).all()
    id_especialidad = request.args.get("id_especialidad", type=int)
    medicos = Medico.query.order_by(Medico.apellido)
    if id_especialidad:
        medicos = medicos.filter(Medico.especialidades.any(Especialidad.id_especialidad == id_especialidad))
    medicos = medicos.all()

    medico = db.session.get(Medico, request.args.get("matricula", "")) if request.args.get("matricula") else None
    fecha = leer_fecha(request.args.get("fecha"))

    # Paso 3: horarios disponibles (horarios del médico menos turnos asignados)
    horarios = servicios.horarios_disponibles(medico, fecha) if medico and fecha else []

    return render_template(
        "turnos/nuevo.html",
        dni=dni,
        paciente=paciente,
        especialidades=especialidades,
        id_especialidad=id_especialidad,
        medicos=medicos,
        medico=medico,
        fecha=fecha,
        hoy=hoy(),
        horarios=horarios,
    )


def _crear_desde_formulario():
    dni = current_user.dni if current_user.rol == "paciente" else request.form.get("dni", "").strip()
    paciente = db.session.get(Paciente, dni)
    medico = db.session.get(Medico, request.form.get("matricula", ""))
    fecha = leer_fecha(request.form.get("fecha"))
    hora = leer_hora(request.form.get("hora"))

    if not (paciente and medico and fecha and hora):
        flash("Faltan datos para registrar el turno.", "error")
        return redirect(url_for("turnos.nuevo"))

    try:
        turno = servicios.crear_turno(paciente, medico, fecha, hora)
    except TurnoError as error:
        flash(str(error), "error")
        return redirect(url_for("turnos.nuevo", dni=dni, matricula=medico.matricula, fecha=fecha.isoformat()))

    flash(
        f"Turno confirmado: {paciente.nombre_completo} con {medico.nombre_completo}, "
        f"{turno.fecha:%d/%m/%Y} a las {turno.hora:%H:%M} hs.",
        "exito",
    )
    return redirect(url_for("turnos.agenda", fecha=turno.fecha.isoformat()))


# ---------- CU-03 Reprogramar turno (Update) ----------
@turnos_bp.route("/<int:id_turno>/reprogramar", methods=["GET", "POST"])
@login_required
def reprogramar(id_turno):
    turno = _obtener_turno_visible(id_turno)
    if not servicios.puede_modificar(current_user, turno):
        abort(403)

    if request.method == "POST":
        fecha = leer_fecha(request.form.get("fecha"))
        hora = leer_hora(request.form.get("hora"))
        if not (fecha and hora):
            flash("Elegí una fecha y un horario.", "error")
            return redirect(url_for("turnos.reprogramar", id_turno=id_turno))
        try:
            servicios.reprogramar_turno(turno, fecha, hora, current_user.rol)
        except TurnoError as error:
            flash(str(error), "error")
            return redirect(url_for("turnos.reprogramar", id_turno=id_turno, fecha=fecha.isoformat()))
        flash(f"Turno reprogramado para el {fecha:%d/%m/%Y} a las {hora:%H:%M} hs.", "exito")
        return redirect(url_for("turnos.agenda", fecha=fecha.isoformat()))

    fecha = leer_fecha(request.args.get("fecha"))
    horarios = servicios.horarios_disponibles(turno.medico, fecha, excluir_turno=turno) if fecha else []
    return render_template("turnos/reprogramar.html", turno=turno, fecha=fecha, hoy=hoy(), horarios=horarios)


# ---------- CU-04 Cancelar turno (Delete lógico) ----------
@turnos_bp.route("/<int:id_turno>/cancelar", methods=["GET", "POST"])
@login_required
def cancelar(id_turno):
    turno = _obtener_turno_visible(id_turno)
    if not servicios.puede_modificar(current_user, turno):
        abort(403)

    if request.method == "POST":
        try:
            servicios.cancelar_turno(turno)
            flash("Turno cancelado. El horario quedó libre.", "exito")
        except TurnoError as error:
            flash(str(error), "error")
        return redirect(url_for("turnos.agenda", fecha=turno.fecha.isoformat()))

    # CU-04 paso 2: pedir confirmación antes de cancelar
    return render_template("turnos/cancelar.html", turno=turno)


# ---------- RF-08 Registrar asistencia ----------
@turnos_bp.route("/<int:id_turno>/asistencia", methods=["POST"])
@login_required
@roles_requeridos("secretaria", "medico")
def asistencia(id_turno):
    turno = _obtener_turno_visible(id_turno)
    try:
        servicios.registrar_asistencia(turno, request.form.get("estado", ""))
        flash(f"Asistencia registrada: {turno.estado}.", "exito")
    except TurnoError as error:
        flash(str(error), "error")
    return redirect(url_for("turnos.agenda", fecha=turno.fecha.isoformat()))
