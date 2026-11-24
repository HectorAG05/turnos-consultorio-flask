"""Lógica de negocio de los turnos (casos de uso CU-01 a CU-04 del SRS).

Las rutas HTML y la API REST usan estas funciones, así las reglas viven en un solo lugar.
"""
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import ESTADOS_ACTIVOS, ESTADOS_QUE_OCUPAN_HORARIO, Turno
from ..utils import ahora

DURACION_TURNO = timedelta(minutes=30)
HORAS_MINIMAS_REPROGRAMACION_PACIENTE = 24


class TurnoError(ValueError):
    """Regla de negocio no cumplida. El mensaje se muestra al usuario."""


def horarios_disponibles(medico, fecha, excluir_turno=None):
    """CU-01 paso 3: horarios de atención del médico menos los turnos ya asignados."""
    franjas = [h for h in medico.horarios if h.dia_semana == fecha.weekday()]
    if not franjas:
        return []

    ocupados = {
        t.hora
        for t in Turno.query.filter(
            Turno.matricula_medico == medico.matricula,
            Turno.fecha == fecha,
            Turno.estado.in_(ESTADOS_QUE_OCUPAN_HORARIO),
        )
        if excluir_turno is None or t.id_turno != excluir_turno.id_turno
    }

    momento_actual = ahora()
    disponibles = []
    for franja in sorted(franjas, key=lambda f: f.hora_inicio):
        inicio = datetime.combine(fecha, franja.hora_inicio)
        fin = datetime.combine(fecha, franja.hora_fin)
        while inicio + DURACION_TURNO <= fin:
            if inicio.time() not in ocupados and inicio > momento_actual:
                disponibles.append(inicio.time())
            inicio += DURACION_TURNO
    return disponibles


def _validar_horario(medico, fecha, hora, excluir_turno=None):
    if datetime.combine(fecha, hora) <= ahora():
        raise TurnoError("No se pueden asignar turnos en fechas u horarios pasados.")
    if hora not in horarios_disponibles(medico, fecha, excluir_turno):
        # CU-01 flujo alternativo 5a: el horario no está en la agenda o ya lo tomó otro usuario
        raise TurnoError("El horario elegido no está disponible. Elegí otro de la lista.")


def _guardar():
    try:
        db.session.commit()
    except IntegrityError as error:
        # Dos usuarios tomaron el mismo horario al mismo tiempo: lo frena el índice único
        db.session.rollback()
        raise TurnoError("Otro usuario acaba de tomar ese horario. Elegí otro.") from error


def crear_turno(paciente, medico, fecha, hora):
    """CU-01 Agendar turno (Create)."""
    _validar_horario(medico, fecha, hora)
    turno = Turno(paciente=paciente, medico=medico, fecha=fecha, hora=hora, estado="confirmado")
    db.session.add(turno)
    _guardar()
    return turno


def reprogramar_turno(turno, fecha, hora, rol_actor):
    """CU-03 Reprogramar turno (Update): mismo médico, nueva fecha y hora."""
    if not turno.esta_activo:
        raise TurnoError(f"No se puede reprogramar un turno en estado «{turno.estado}».")

    if rol_actor == "paciente":
        # CU-03 flujo alternativo 1a: el paciente necesita 24 h de anticipación
        horas_restantes = (datetime.combine(turno.fecha, turno.hora) - ahora()).total_seconds() / 3600
        if horas_restantes < HORAS_MINIMAS_REPROGRAMACION_PACIENTE:
            raise TurnoError(
                "Faltan menos de 24 horas para el turno. Comunicate con recepción para reprogramarlo."
            )

    _validar_horario(turno.medico, fecha, hora, excluir_turno=turno)
    turno.fecha = fecha
    turno.hora = hora
    turno.estado = "reprogramado"
    _guardar()
    return turno


def cancelar_turno(turno):
    """CU-04 Cancelar turno (Delete lógico): no se elimina, queda como «cancelado» (RNF-06)."""
    if not turno.esta_activo:
        raise TurnoError(f"El turno ya está en estado «{turno.estado}».")
    turno.estado = "cancelado"
    _guardar()
    return turno


def registrar_asistencia(turno, estado):
    """RF-08: marcar el turno como atendido o ausente."""
    if estado not in ("atendido", "ausente"):
        raise TurnoError("La asistencia solo puede ser «atendido» o «ausente».")
    if turno.estado not in ESTADOS_ACTIVOS:
        raise TurnoError(f"No se puede registrar asistencia en un turno «{turno.estado}».")
    turno.estado = estado
    _guardar()
    return turno


def turnos_visibles(usuario):
    """RNF-02: el paciente ve sus turnos, el médico su agenda y la secretaria todo."""
    consulta = Turno.query
    if usuario.rol == "paciente":
        consulta = consulta.filter(Turno.dni_paciente == usuario.dni)
    elif usuario.rol == "medico":
        consulta = consulta.filter(Turno.matricula_medico == usuario.matricula)
    return consulta


def puede_ver(usuario, turno):
    if usuario.rol == "secretaria":
        return True
    if usuario.rol == "medico":
        return turno.matricula_medico == usuario.matricula
    return turno.dni_paciente == usuario.dni


def puede_modificar(usuario, turno):
    """Reprogramar o cancelar: el paciente (sus turnos) o la secretaria."""
    if usuario.rol == "secretaria":
        return True
    return usuario.rol == "paciente" and turno.dni_paciente == usuario.dni
