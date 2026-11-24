"""Control de acceso por rol (RNF-02)."""
from functools import wraps

from flask import abort
from flask_login import current_user


def roles_requeridos(*roles):
    """Permite el acceso solo a los roles indicados. Usar después de @login_required."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if current_user.rol not in roles:
                abort(403)
            return vista(*args, **kwargs)

        return envoltura

    return decorador
