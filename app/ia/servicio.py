"""Uso del modelo de ausentismo entrenado con ml/train_model.py.

El modelo se carga UNA sola vez al iniciar la app (create_app) y queda guardado en
app.extensions; cada predicción solo lo consulta.
"""
import logging

import joblib
from flask import current_app

from ..models import Turno

log = logging.getLogger(__name__)

CLAVE_EXTENSION = "modelo_ausentismo"

# Rango válido de cada variable de entrada
LIMITES = {
    "dias_anticipacion": (0, 365),
    "hora": (0, 23),
    "tiene_obra_social": (0, 1),
    "ausencias_previas": (0, 50),
}


class DatosPrediccionInvalidos(ValueError):
    pass


def cargar_modelo(app):
    ruta = app.config["MODEL_PATH"]
    try:
        app.extensions[CLAVE_EXTENSION] = joblib.load(ruta)
        log.info("Modelo de ausentismo cargado desde %s", ruta)
    except FileNotFoundError:
        app.extensions[CLAVE_EXTENSION] = None
        log.warning("No se encontró el modelo en %s. Ejecutá: python ml/train_model.py", ruta)


def obtener_modelo():
    return current_app.extensions.get(CLAVE_EXTENSION)


def validar_datos(datos):
    """Convierte y valida los datos de entrada. Devuelve un dict con números."""
    limpios = {}
    for campo, (minimo, maximo) in LIMITES.items():
        valor = datos.get(campo)
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            raise DatosPrediccionInvalidos(f"El campo «{campo}» debe ser un número entero.") from None
        if not minimo <= numero <= maximo:
            raise DatosPrediccionInvalidos(f"El campo «{campo}» debe estar entre {minimo} y {maximo}.")
        limpios[campo] = numero
    return limpios


def predecir_ausentismo(datos):
    """Devuelve la probabilidad (0 a 1) de que el paciente falte al turno."""
    paquete = obtener_modelo()
    if paquete is None:
        raise RuntimeError("El modelo de IA no está disponible.")
    fila = [[float(datos[nombre]) for nombre in paquete["features"]]]
    return float(paquete["modelo"].predict_proba(fila)[0][1])


def nivel_de_riesgo(probabilidad):
    if probabilidad >= 0.5:
        return "alto"
    if probabilidad >= 0.25:
        return "medio"
    return "bajo"


def datos_de_turno(turno):
    """Arma las variables de entrada del modelo a partir de un turno guardado."""
    ausencias_previas = Turno.query.filter(
        Turno.dni_paciente == turno.dni_paciente,
        Turno.estado == "ausente",
        Turno.id_turno != turno.id_turno,
    ).count()
    return {
        "dias_anticipacion": max((turno.fecha - turno.creado_en.date()).days, 0),
        "hora": turno.hora.hour,
        "tiene_obra_social": 1 if turno.paciente.id_obra_social else 0,
        "ausencias_previas": ausencias_previas,
    }


def riesgo_de_turno(turno):
    """Probabilidad de ausentismo de un turno, o None si el modelo no está cargado."""
    if obtener_modelo() is None:
        return None
    return predecir_ausentismo(datos_de_turno(turno))
