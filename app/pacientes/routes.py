"""Blueprint de pacientes (RF-01 y RF-10): CRUD completo, solo para la secretaria."""
import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..auth.decoradores import roles_requeridos
from ..extensions import db
from ..models import ObraSocial, Paciente, Turno, Usuario

pacientes_bp = Blueprint("pacientes", __name__)

PATRON_DNI = re.compile(r"^\d{7,8}$")
PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_paciente(datos, es_alta):
    errores = []
    obligatorios = ("dni", "nombre", "apellido", "telefono") if es_alta else ("nombre", "apellido", "telefono")
    for campo in obligatorios:
        if not datos.get(campo, "").strip():
            errores.append(f"El campo «{campo}» es obligatorio.")
    if es_alta and datos.get("dni") and not PATRON_DNI.match(datos["dni"]):
        errores.append("El DNI debe tener 7 u 8 números, sin puntos.")
    if es_alta and datos.get("dni") and db.session.get(Paciente, datos["dni"]):
        errores.append("Ya existe un paciente con ese DNI.")
    if datos.get("email") and not PATRON_EMAIL.match(datos["email"].strip()):
        errores.append("El email no tiene un formato válido.")
    return errores


def aplicar_datos(paciente, datos):
    paciente.nombre = datos["nombre"].strip()
    paciente.apellido = datos["apellido"].strip()
    paciente.telefono = datos["telefono"].strip()
    paciente.email = datos.get("email", "").strip() or None
    paciente.id_obra_social = int(datos["id_obra_social"]) if datos.get("id_obra_social") else None


# ---------- Read ----------
@pacientes_bp.route("/")
@login_required
@roles_requeridos("secretaria")
def lista():
    busqueda = request.args.get("q", "").strip()
    consulta = Paciente.query
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(
            Paciente.dni.like(patron) | Paciente.apellido.ilike(patron) | Paciente.nombre.ilike(patron)
        )
    pacientes = consulta.order_by(Paciente.apellido, Paciente.nombre).all()
    return render_template("pacientes/lista.html", pacientes=pacientes, busqueda=busqueda)


@pacientes_bp.route("/<dni>")
@login_required
@roles_requeridos("secretaria")
def ficha(dni):
    """RF-10 / DF-12: ficha del paciente a partir de su DNI."""
    paciente = db.session.get(Paciente, dni) or abort(404)
    turnos = Turno.query.filter_by(dni_paciente=dni).order_by(Turno.fecha.desc(), Turno.hora.desc()).all()
    return render_template("pacientes/ficha.html", paciente=paciente, turnos=turnos)


# ---------- Create ----------
@pacientes_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@roles_requeridos("secretaria")
def nuevo():
    obras_sociales = ObraSocial.query.order_by(ObraSocial.nombre).all()
    datos = request.form.to_dict() if request.method == "POST" else {"dni": request.args.get("dni", "")}

    if request.method == "POST":
        errores = validar_paciente(datos, es_alta=True)
        if errores:
            for error in errores:
                flash(error, "error")
            return render_template("pacientes/form.html", datos=datos, obras_sociales=obras_sociales, es_alta=True), 400
        paciente = Paciente(dni=datos["dni"])
        aplicar_datos(paciente, datos)
        db.session.add(paciente)
        db.session.commit()
        flash(f"Paciente {paciente.nombre_completo} registrado.", "exito")
        # Retoma el alta de turno (CU-01 flujo alternativo 1a)
        return redirect(url_for("turnos.nuevo", dni=paciente.dni))

    return render_template("pacientes/form.html", datos=datos, obras_sociales=obras_sociales, es_alta=True)


# ---------- Update ----------
@pacientes_bp.route("/<dni>/editar", methods=["GET", "POST"])
@login_required
@roles_requeridos("secretaria")
def editar(dni):
    paciente = db.session.get(Paciente, dni) or abort(404)
    obras_sociales = ObraSocial.query.order_by(ObraSocial.nombre).all()

    if request.method == "POST":
        datos = request.form.to_dict()
        datos["dni"] = dni
        errores = validar_paciente(datos, es_alta=False)
        if errores:
            for error in errores:
                flash(error, "error")
            return render_template("pacientes/form.html", datos=datos, obras_sociales=obras_sociales, es_alta=False), 400
        aplicar_datos(paciente, datos)
        db.session.commit()
        flash("Datos del paciente actualizados.", "exito")
        return redirect(url_for("pacientes.ficha", dni=dni))

    datos = paciente.to_dict()
    datos["email"] = datos["email"] or ""
    datos["id_obra_social"] = str(datos["id_obra_social"] or "")
    return render_template("pacientes/form.html", datos=datos, obras_sociales=obras_sociales, es_alta=False)


# ---------- Delete ----------
@pacientes_bp.route("/<dni>/eliminar", methods=["POST"])
@login_required
@roles_requeridos("secretaria")
def eliminar(dni):
    paciente = db.session.get(Paciente, dni) or abort(404)
    # Integridad: un paciente con turnos no se borra, porque los turnos son su historial
    if Turno.query.filter_by(dni_paciente=dni).count():
        flash("No se puede eliminar: el paciente tiene turnos en su historial.", "error")
        return redirect(url_for("pacientes.ficha", dni=dni))

    Usuario.query.filter_by(dni=dni).delete()
    db.session.delete(paciente)
    db.session.commit()
    flash(f"Paciente {paciente.nombre_completo} eliminado.", "exito")
    return redirect(url_for("pacientes.lista"))
