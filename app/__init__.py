"""App Factory: create_app() arma la aplicación, registra extensiones y blueprints."""
import os

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from config import Config

from .extensions import bcrypt, db, login_manager
from .seguridad import init_csrf
from .utils import formatear_fecha, formatear_hora, nombre_dia


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("Falta la variable SECRET_KEY. Copiá .env.example como .env y completala.")
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)
    _configurar_login(app)
    init_csrf(app)
    _registrar_blueprints(app)
    _registrar_errores(app)
    _registrar_filtros(app)

    # El modelo de IA se carga UNA vez, al iniciar la aplicación
    from .ia.servicio import cargar_modelo

    cargar_modelo(app)

    with app.app_context():
        db.create_all()
        from .seed import cargar_datos_iniciales

        cargar_datos_iniciales()

    @app.route("/")
    def inicio():
        if current_user.is_authenticated:
            return redirect(url_for("turnos.agenda"))
        return redirect(url_for("auth.login"))

    return app


def _configurar_login(app):
    from .models import Usuario

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Iniciá sesión para continuar."
    login_manager.login_message_category = "aviso"

    @login_manager.user_loader
    def cargar_usuario(id_usuario):
        return db.session.get(Usuario, int(id_usuario))

    @login_manager.unauthorized_handler
    def no_autorizado():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Iniciá sesión para usar la API."}), 401
        return redirect(url_for("auth.login", next=request.full_path))


def _registrar_blueprints(app):
    from .api.routes import api_bp
    from .auth.routes import auth_bp
    from .ia.routes import ia_bp
    from .pacientes.routes import pacientes_bp
    from .turnos.routes import turnos_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(turnos_bp, url_prefix="/turnos")
    app.register_blueprint(pacientes_bp, url_prefix="/pacientes")
    app.register_blueprint(ia_bp, url_prefix="/ia")
    app.register_blueprint(api_bp, url_prefix="/api")


def _registrar_errores(app):
    mensajes = {
        400: "La solicitud no es válida.",
        403: "No tenés permiso para ver esta página.",
        404: "La página que buscás no existe.",
        405: "Método no permitido.",
        500: "Ocurrió un error inesperado. Intentá de nuevo más tarde.",
    }

    def manejar(error):
        codigo = getattr(error, "code", 500) or 500
        descripcion = getattr(error, "description", None)
        mensaje = descripcion if codigo == 400 and descripcion else mensajes.get(codigo, mensajes[500])
        if request.path.startswith("/api/"):
            return jsonify({"error": mensaje}), codigo
        return render_template("errores/error.html", codigo=codigo, mensaje=mensaje), codigo

    for codigo in mensajes:
        app.register_error_handler(codigo, manejar)


def _registrar_filtros(app):
    app.jinja_env.filters["fecha"] = formatear_fecha
    app.jinja_env.filters["hora"] = formatear_hora
    app.jinja_env.filters["dia"] = nombre_dia
