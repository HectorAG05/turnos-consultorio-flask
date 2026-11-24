"""Blueprint de IA: formulario para predecir el ausentismo en tiempo real."""
from flask import Blueprint, flash, render_template, request
from flask_login import login_required

from ..auth.decoradores import roles_requeridos
from .servicio import (
    DatosPrediccionInvalidos,
    nivel_de_riesgo,
    obtener_modelo,
    predecir_ausentismo,
    validar_datos,
)

ia_bp = Blueprint("ia", __name__)


@ia_bp.route("/prediccion", methods=["GET", "POST"])
@login_required
@roles_requeridos("secretaria", "medico")
def prediccion():
    paquete = obtener_modelo()
    datos = {"dias_anticipacion": 7, "hora": 10, "tiene_obra_social": 1, "ausencias_previas": 0}
    resultado = None

    if request.method == "POST":
        datos = request.form.to_dict()
        try:
            limpios = validar_datos(datos)
            probabilidad = predecir_ausentismo(limpios)
            resultado = {"probabilidad": probabilidad, "nivel": nivel_de_riesgo(probabilidad)}
        except DatosPrediccionInvalidos as error:
            flash(str(error), "error")
        except RuntimeError as error:
            flash(str(error), "error")

    return render_template(
        "ia/prediccion.html",
        datos=datos,
        resultado=resultado,
        metricas=paquete["metricas"] if paquete else None,
    )
