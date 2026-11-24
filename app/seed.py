"""Datos iniciales: catálogos, médicos, pacientes, usuarios de demostración y turnos de ejemplo.

Se cargan solo si la base está vacía, así que es seguro ejecutarlo en cada inicio.
Los nombres coinciden con los prototipos del SRS (sección 5).
"""
import logging
from datetime import datetime, time, timedelta

from flask import current_app

from .extensions import db
from .models import Especialidad, Horario, Medico, ObraSocial, Paciente, Turno, Usuario
from .utils import hoy

log = logging.getLogger(__name__)

OBRAS_SOCIALES = ["OSDE", "Swiss Medical", "Galeno", "IOMA", "PAMI"]
ESPECIALIDADES = ["Clínica médica", "Cardiología", "Pediatría", "Dermatología"]

# matricula, título, nombre, apellido, especialidades, [(días, inicio, fin)]
MEDICOS = [
    ("MN-1001", "Dra.", "Silvia", "Gómez", ["Clínica médica"], [((0, 1, 2, 3, 4), "09:00", "12:00")]),
    ("MN-1002", "Dr.", "Martín", "Pérez", ["Cardiología", "Clínica médica"], [((0, 2, 4), "14:00", "18:00")]),
    ("MN-1003", "Dra.", "Paula", "Ríos", ["Pediatría"], [((1, 3), "10:00", "13:00"), ((5,), "09:00", "12:00")]),
    ("MN-1004", "Dr.", "Andrés", "Molina", ["Dermatología"], [((0, 1, 2, 3), "16:00", "19:00")]),
]

# dni, nombre, apellido, teléfono, email, obra social (None = particular)
PACIENTES = [
    ("30111222", "María", "López", "11 4555-1020", "maria.lopez@mail.com", "OSDE"),
    ("28333444", "Carlos", "Díaz", "11 4666-3040", None, "Swiss Medical"),
    ("35555666", "Ana", "Torres", "11 4777-5060", "ana.torres@mail.com", None),
    ("27777888", "Jorge", "Ruiz", "11 4888-7080", None, "Galeno"),
    ("32456789", "Lucía", "Fernández", "11 4999-9010", "lucia.fernandez@mail.com", None),
]

# usuario, rol, dni, matrícula
USUARIOS = [
    ("laura", "secretaria", None, None),
    ("sgomez", "medico", None, "MN-1001"),
    ("mperez", "medico", None, "MN-1002"),
    ("lucia", "paciente", "32456789", None),
]


def _hora(texto):
    return datetime.strptime(texto, "%H:%M").time()


def _cargar_catalogos():
    if ObraSocial.query.first():
        return
    db.session.add_all(ObraSocial(nombre=n) for n in OBRAS_SOCIALES)
    db.session.add_all(Especialidad(nombre=n) for n in ESPECIALIDADES)
    db.session.commit()


def _cargar_medicos_y_pacientes():
    if Medico.query.first():
        return
    especialidades = {e.nombre: e for e in Especialidad.query.all()}
    obras = {o.nombre: o for o in ObraSocial.query.all()}

    for matricula, titulo, nombre, apellido, esps, franjas in MEDICOS:
        medico = Medico(matricula=matricula, titulo=titulo, nombre=nombre, apellido=apellido)
        medico.especialidades = [especialidades[e] for e in esps]
        for dias, inicio, fin in franjas:
            for dia in dias:
                medico.horarios.append(Horario(dia_semana=dia, hora_inicio=_hora(inicio), hora_fin=_hora(fin)))
        db.session.add(medico)

    for dni, nombre, apellido, telefono, email, obra in PACIENTES:
        db.session.add(
            Paciente(
                dni=dni,
                nombre=nombre,
                apellido=apellido,
                telefono=telefono,
                email=email,
                obra_social=obras.get(obra) if obra else None,
            )
        )
    db.session.commit()
    _cargar_turnos_de_ejemplo()


def _cargar_turnos_de_ejemplo():
    """Turnos de las últimas y próximas dos semanas, con estados variados."""
    medicos = Medico.query.order_by(Medico.matricula).all()
    pacientes = Paciente.query.order_by(Paciente.dni).all()
    anticipaciones = [2, 5, 15, 30, 1, 10, 21]
    base = hoy()
    contador = 0

    for desplazamiento in range(-14, 15):
        fecha = base + timedelta(days=desplazamiento)
        for medico in medicos:
            franja = next((h for h in medico.horarios if h.dia_semana == fecha.weekday()), None)
            if franja is None:
                continue
            for orden in range(2):
                inicio = datetime.combine(fecha, franja.hora_inicio) + timedelta(minutes=60 * orden + 30 * (desplazamiento % 2))
                if (inicio + timedelta(minutes=30)).time() > franja.hora_fin:
                    continue
                paciente = pacientes[contador % len(pacientes)]
                anticipacion = anticipaciones[contador % len(anticipaciones)]
                contador += 1

                if desplazamiento < 0:
                    # Carlos Díaz falta seguido: el modelo le asigna más riesgo
                    falto = (paciente.dni == "28333444" and contador % 2 == 0) or contador % 7 == 0
                    estado = "ausente" if falto else "atendido"
                elif contador % 11 == 0:
                    estado = "cancelado"
                elif contador % 9 == 0:
                    estado = "reprogramado"
                else:
                    estado = "confirmado"

                db.session.add(
                    Turno(
                        paciente=paciente,
                        medico=medico,
                        fecha=fecha,
                        hora=inicio.time(),
                        estado=estado,
                        creado_en=datetime.combine(fecha - timedelta(days=anticipacion), time(10, 0)),
                    )
                )
    db.session.commit()


def _cargar_usuarios():
    if Usuario.query.first():
        return
    password = current_app.config.get("SEED_PASSWORD")
    if not password:
        log.warning("SEED_PASSWORD no está definida: no se crean los usuarios de demostración.")
        return
    for username, rol, dni, matricula in USUARIOS:
        usuario = Usuario(username=username, rol=rol, dni=dni, matricula=matricula)
        usuario.set_password(password)
        db.session.add(usuario)
    db.session.commit()


def cargar_datos_iniciales():
    _cargar_catalogos()
    _cargar_medicos_y_pacientes()
    _cargar_usuarios()
