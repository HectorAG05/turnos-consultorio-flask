"""Utilidades de fecha y hora con la zona horaria del consultorio."""
from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_HORARIA = ZoneInfo("America/Argentina/Buenos_Aires")

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def ahora():
    """Fecha y hora actual del consultorio, sin zona (así se guardan en la base)."""
    return datetime.now(ZONA_HORARIA).replace(tzinfo=None, microsecond=0)


def hoy():
    return ahora().date()


def formatear_fecha(valor):
    return valor.strftime("%d/%m/%Y") if valor else ""


def formatear_hora(valor):
    return valor.strftime("%H:%M") if valor else ""


def nombre_dia(valor):
    return DIAS_SEMANA[valor.weekday()] if valor else ""
