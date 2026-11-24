"""Modelo de datos: implementa el DER y el diccionario de datos del SRS.

Almacén D1 -> Paciente, D2 -> Medico (+ Horario, Especialidad), D3 -> Turno.
Usuario implementa la tabla de credenciales prevista en el SRS (sección 2.3, RNF-02).
"""
from flask_login import UserMixin

from .extensions import bcrypt, db
from .utils import ahora

# Dominio "estado" del diccionario de datos
ESTADOS = ("confirmado", "reprogramado", "cancelado", "atendido", "ausente")
ESTADOS_ACTIVOS = ("confirmado", "reprogramado")  # se pueden reprogramar o cancelar
ESTADOS_QUE_OCUPAN_HORARIO = ("confirmado", "reprogramado", "atendido", "ausente")

ROLES = ("secretaria", "medico", "paciente")

# Relación N:M "Ejerce" entre MÉDICO y ESPECIALIDAD (tabla intermedia con clave compuesta)
medico_especialidad = db.Table(
    "medico_especialidad",
    db.Column("matricula", db.String(20), db.ForeignKey("medicos.matricula"), primary_key=True),
    db.Column("id_especialidad", db.Integer, db.ForeignKey("especialidades.id_especialidad"), primary_key=True),
)


class ObraSocial(db.Model):
    __tablename__ = "obras_sociales"

    id_obra_social = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), unique=True, nullable=False)


class Especialidad(db.Model):
    __tablename__ = "especialidades"

    id_especialidad = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), unique=True, nullable=False)


class Paciente(db.Model):
    __tablename__ = "pacientes"

    dni = db.Column(db.String(10), primary_key=True)
    nombre = db.Column(db.String(60), nullable=False)
    apellido = db.Column(db.String(60), nullable=False)
    telefono = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    id_obra_social = db.Column(db.Integer, db.ForeignKey("obras_sociales.id_obra_social"))

    obra_social = db.relationship("ObraSocial")
    turnos = db.relationship("Turno", back_populates="paciente")

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def cobertura(self):
        return self.obra_social.nombre if self.obra_social else "Particular (sin obra social)"

    def to_dict(self):
        return {
            "dni": self.dni,
            "nombre": self.nombre,
            "apellido": self.apellido,
            "telefono": self.telefono,
            "email": self.email,
            "id_obra_social": self.id_obra_social,
            "obra_social": self.obra_social.nombre if self.obra_social else None,
        }


class Medico(db.Model):
    __tablename__ = "medicos"

    matricula = db.Column(db.String(20), primary_key=True)
    nombre = db.Column(db.String(60), nullable=False)
    apellido = db.Column(db.String(60), nullable=False)
    titulo = db.Column(db.String(5), nullable=False, default="Dr.")

    especialidades = db.relationship("Especialidad", secondary=medico_especialidad, lazy="selectin")
    # Atributo multivaluado "Horario" del DER
    horarios = db.relationship("Horario", cascade="all, delete-orphan", lazy="selectin")
    turnos = db.relationship("Turno", back_populates="medico")

    @property
    def nombre_completo(self):
        return f"{self.titulo} {self.nombre} {self.apellido}"


class Horario(db.Model):
    """Franja de atención semanal: horario = dia_semana + hora_inicio + hora_fin."""

    __tablename__ = "horarios"

    id_horario = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(20), db.ForeignKey("medicos.matricula"), nullable=False)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0 = lunes ... 5 = sábado
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)


class Turno(db.Model):
    __tablename__ = "turnos"
    # Un médico no puede tener dos turnos activos en la misma fecha y hora.
    # Los cancelados no cuentan: liberan el horario (CU-04).
    __table_args__ = (
        db.Index(
            "uq_turno_horario_ocupado",
            "matricula_medico",
            "fecha",
            "hora",
            unique=True,
            sqlite_where=db.text("estado != 'cancelado'"),
            postgresql_where=db.text("estado != 'cancelado'"),
        ),
    )

    id_turno = db.Column(db.Integer, primary_key=True)
    dni_paciente = db.Column(db.String(10), db.ForeignKey("pacientes.dni"), nullable=False)
    matricula_medico = db.Column(db.String(20), db.ForeignKey("medicos.matricula"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    estado = db.Column(db.String(15), nullable=False, default="confirmado")
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora)

    paciente = db.relationship("Paciente", back_populates="turnos")
    medico = db.relationship("Medico", back_populates="turnos")

    @property
    def esta_activo(self):
        return self.estado in ESTADOS_ACTIVOS

    def to_dict(self):
        return {
            "id_turno": self.id_turno,
            "dni_paciente": self.dni_paciente,
            "paciente": self.paciente.nombre_completo,
            "matricula_medico": self.matricula_medico,
            "medico": self.medico.nombre_completo,
            "fecha": self.fecha.isoformat(),
            "hora": self.hora.strftime("%H:%M"),
            "estado": self.estado,
        }


class Usuario(UserMixin, db.Model):
    """Usuario = @nombre_usuario + contraseña_cifrada + rol + [dni | matricula]."""

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    rol = db.Column(db.String(15), nullable=False)
    dni = db.Column(db.String(10), db.ForeignKey("pacientes.dni"))
    matricula = db.Column(db.String(20), db.ForeignKey("medicos.matricula"))

    paciente = db.relationship("Paciente")
    medico = db.relationship("Medico")

    def set_password(self, password):
        # Bcrypt: la contraseña nunca se guarda en texto plano
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def nombre_visible(self):
        if self.rol == "paciente" and self.paciente:
            return self.paciente.nombre_completo
        if self.rol == "medico" and self.medico:
            return self.medico.nombre_completo
        return self.username.capitalize()
