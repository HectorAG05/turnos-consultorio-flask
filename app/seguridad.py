"""Protección CSRF simple para los formularios HTML.

Cada sesión recibe un token aleatorio; todo POST de un formulario debe enviarlo en el
campo oculto «_csrf». Así otro sitio no puede enviar formularios en nombre del usuario.
La API JSON (/api/...) queda afuera: usa la cookie de sesión con SameSite=Lax.
"""
import secrets

from flask import abort, request, session


def obtener_token_csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def init_csrf(app):
    app.jinja_env.globals["csrf_token"] = obtener_token_csrf

    @app.before_request
    def verificar_csrf():
        if not app.config.get("CSRF_ENABLED", True):
            return
        if request.method == "POST" and not request.path.startswith("/api/"):
            enviado = request.form.get("_csrf", "")
            esperado = session.get("_csrf", "")
            if not esperado or not secrets.compare_digest(enviado, esperado):
                abort(400, description="El formulario venció. Recargá la página e intentá de nuevo.")
