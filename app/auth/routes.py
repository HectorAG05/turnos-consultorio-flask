"""Blueprint de autenticación: registro, login y logout con Flask-Login y Bcrypt."""
import re
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import ObraSocial, Paciente, Usuario

auth_bp = Blueprint("auth", __name__)

LARGO_MINIMO_PASSWORD = 8
PATRON_DNI = re.compile(r"^\d{7,8}$")
PATRON_USUARIO = re.compile(r"^[a-zA-Z0-9_.]{3,40}$")


def _destino_seguro(destino):
    """Evita redirecciones a otros sitios (open redirect) con el parámetro ?next=."""
    if destino and not urlsplit(destino).netloc and destino.startswith("/"):
        return destino
    return url_for("turnos.agenda")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("turnos.agenda"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        usuario = Usuario.query.filter_by(username=username).first()

        # Mismo mensaje para usuario inexistente o contraseña incorrecta
        if usuario is None or not usuario.check_password(password):
            flash("Usuario o contraseña incorrectos.", "error")
            return render_template("auth/login.html", username=username), 401

        login_user(usuario)
        flash(f"¡Hola, {usuario.nombre_visible}!", "exito")
        return redirect(_destino_seguro(request.args.get("next")))

    return render_template("auth/login.html")


@auth_bp.route("/registro", methods=["GET", "POST"])
def registro():
    """Alta de un paciente con su usuario (rol paciente)."""
    if current_user.is_authenticated:
        return redirect(url_for("turnos.agenda"))

    obras_sociales = ObraSocial.query.order_by(ObraSocial.nombre).all()
    datos = request.form.to_dict()

    if request.method == "POST":
        errores = _validar_registro(datos)
        if errores:
            for error in errores:
                flash(error, "error")
            return render_template("auth/registro.html", datos=datos, obras_sociales=obras_sociales), 400

        paciente = db.session.get(Paciente, datos["dni"])
        if paciente is None:
            paciente = Paciente(
                dni=datos["dni"],
                nombre=datos["nombre"].strip(),
                apellido=datos["apellido"].strip(),
                telefono=datos["telefono"].strip(),
                email=datos.get("email", "").strip() or None,
                id_obra_social=int(datos["id_obra_social"]) if datos.get("id_obra_social") else None,
            )
            db.session.add(paciente)

        usuario = Usuario(username=datos["username"].strip().lower(), rol="paciente", dni=paciente.dni)
        usuario.set_password(datos["password"])
        db.session.add(usuario)
        db.session.commit()

        login_user(usuario)
        flash("Cuenta creada. Ya podés pedir turnos.", "exito")
        return redirect(url_for("turnos.agenda"))

    return render_template("auth/registro.html", datos=datos, obras_sociales=obras_sociales)


def _validar_registro(datos):
    errores = []
    for campo in ("dni", "nombre", "apellido", "telefono", "username", "password"):
        if not datos.get(campo, "").strip():
            errores.append(f"El campo «{campo}» es obligatorio.")
    if errores:
        return errores

    if not PATRON_DNI.match(datos["dni"]):
        errores.append("El DNI debe tener 7 u 8 números, sin puntos.")
    if not PATRON_USUARIO.match(datos["username"].strip()):
        errores.append("El usuario debe tener entre 3 y 40 letras, números, puntos o guiones bajos.")
    if len(datos["password"]) < LARGO_MINIMO_PASSWORD:
        errores.append(f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres.")
    if datos["password"] != datos.get("password2"):
        errores.append("Las contraseñas no coinciden.")
    if Usuario.query.filter_by(username=datos["username"].strip().lower()).first():
        errores.append("Ese nombre de usuario ya está en uso.")
    if Usuario.query.filter_by(dni=datos["dni"]).first():
        errores.append("Ya existe una cuenta para ese DNI.")
    return errores


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "exito")
    return redirect(url_for("auth.login"))
