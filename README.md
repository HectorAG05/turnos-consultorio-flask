# Sistema de Gestión de Turnos para Consultorio Médico — Prototipo Flask + IA

Segunda entrega de **Análisis y Metodología de Sistemas**. Prototipo funcional y recortado del sistema definido en el SRS de la primera entrega (*Sistema de Gestión de Turnos para Consultorio Médico*, versión 1.0).

- **Aplicación en producción (Render):** _completar con el link_
- **Repositorio:** _completar con el link_

## Qué incluye

| Requisito de la consigna | Implementación |
|---|---|
| Flask + entorno virtual `.venv` | `run.py`, `requirements.txt` |
| CRUD completo sobre base de datos (SQLAlchemy) | **Turnos** (CU-01 a CU-04) y **Pacientes**, en pantallas y en una API REST |
| POST / GET / PUT / PATCH / DELETE | API REST en `/api/turnos` y `/api/pacientes` (ver tabla abajo) |
| Plantillas Jinja2 y formularios HTML | `app/templates/` |
| Modelo de IA con scikit-learn guardado con joblib | Regresión logística de **ausentismo** (`ml/train_model.py`), cargada al iniciar la app |
| Endpoint de predicción en tiempo real | `/ia/prediccion` (formulario) y `POST /api/prediccion` (JSON); además, el riesgo de cada turno aparece en la agenda |
| Secretos en `.env` con python-dotenv | `config.py`, `.env.example`, `.env` en `.gitignore` |
| Login con contraseñas en Bcrypt | Flask-Login + Flask-Bcrypt, roles secretaria / médico / paciente |
| Blueprints y App Factory | `create_app()` en `app/__init__.py`; blueprints `auth`, `turnos`, `pacientes`, `ia`, `api` |
| Despliegue en Render con PostgreSQL | `render.yaml`, `gunicorn run:app`, `DATABASE_URL` |

## Trazabilidad: del SRS al código

El requisito principal del SRS es la **gestión de turnos**. Este prototipo lo recorre desde la base de datos hasta la interfaz.

| SRS | Base de datos | Lógica | Interfaz / API |
|---|---|---|---|
| RF-03 / CU-01 Agendar turno validando disponibilidad | `turnos` (D3), `horarios` (D2) | `servicios.crear_turno`, `horarios_disponibles` | `/turnos/nuevo` (3 pasos), `POST /api/turnos` |
| RF-06 / CU-02 Consultar turnos y agenda según el rol | `turnos` | `servicios.turnos_visibles` | `/turnos/`, `GET /api/turnos` |
| RF-05 / CU-03 Reprogramar (24 h si reprograma el paciente) | `turnos.fecha`, `turnos.hora`, `turnos.estado` | `servicios.reprogramar_turno` | `/turnos/<id>/reprogramar`, `PUT /api/turnos/<id>` |
| RF-04 / CU-04 Cancelar sin borrar (RNF-06) | `turnos.estado = cancelado` | `servicios.cancelar_turno` | `/turnos/<id>/cancelar`, `DELETE /api/turnos/<id>` |
| RF-08 Registrar asistencia | `turnos.estado` | `servicios.registrar_asistencia` | Botones de la agenda, `PATCH /api/turnos/<id>` |
| RF-01 / RF-10 Alta, modificación y consulta de pacientes | `pacientes` (D1), `obras_sociales` | `app/pacientes/routes.py` | `/pacientes/`, `/api/pacientes` |
| RNF-02 Acceso con usuario, contraseña y rol | `usuarios` (tabla prevista en la sección 2.3 del SRS) | `auth/decoradores.py` | `/auth/login`, `/auth/registro` |
| Propósito del SRS: reducir el ausentismo | `turnos` (historial de asistencias) | `ia/servicio.py` | Columna «Riesgo de ausencia», `/ia/prediccion` |

**Fuera de este prototipo** (sí están en el SRS): envío real de recordatorios por SMS o email (RF-07), validación de cobertura con obras sociales (RF-09) y carga de médicos desde la interfaz (RF-02; los médicos se cargan como datos iniciales).

## API REST

Requiere sesión iniciada (cookie de login). Sin sesión responde `401`.

| Método | Endpoint | Acción |
|---|---|---|
| GET | `/api/turnos?fecha=AAAA-MM-DD` | Listar turnos visibles para el usuario |
| GET | `/api/turnos/<id>` | Ver un turno |
| POST | `/api/turnos` | Crear: `{"dni_paciente", "matricula_medico", "fecha", "hora"}` → `201` |
| PUT | `/api/turnos/<id>` | Reprogramar: `{"fecha", "hora"}` |
| PATCH | `/api/turnos/<id>` | Asistencia: `{"estado": "atendido" \| "ausente"}` |
| DELETE | `/api/turnos/<id>` | Cancelar (baja lógica) |
| GET / POST | `/api/pacientes` | Listar / crear pacientes |
| PUT / DELETE | `/api/pacientes/<dni>` | Modificar / eliminar (si no tiene turnos) → `204` |
| POST | `/api/prediccion` | `{"dias_anticipacion", "hora", "tiene_obra_social", "ausencias_previas"}` → probabilidad |

## Modelo de IA

- **Problema:** estimar la probabilidad de que un paciente **no se presente** a su turno. Así la secretaria sabe a quién conviene llamar para confirmar.
- **Modelo:** `Pipeline(StandardScaler + LogisticRegression)` de scikit-learn, guardado con `joblib` en `models/modelo_ausentismo.joblib`.
- **Variables:** días de anticipación del pedido, hora del turno, si tiene obra social y cantidad de ausencias previas.
- **Datos:** el consultorio todavía no tiene historial, así que `ml/train_model.py` genera un **dataset sintético** (3000 turnos, semilla 42) con reglas documentadas en el mismo archivo. Queda guardado en `ml/data/turnos_historicos.csv`.
- **Métricas** (25 % de prueba): accuracy 0,745 y ROC-AUC 0,778.
- **Carga:** el modelo se carga una sola vez, en `create_app()`, y queda en `app.extensions`.

Para reentrenarlo:

```bash
python ml/train_model.py
```

## Estructura

```
├── run.py                  # Punto de entrada (gunicorn run:app)
├── config.py               # Configuración desde variables de entorno
├── requirements.txt
├── render.yaml             # Servicio web + PostgreSQL en Render
├── .env.example            # Variables necesarias (el .env real no se sube)
├── app/
│   ├── __init__.py         # App Factory: create_app()
│   ├── extensions.py       # db, bcrypt, login_manager
│   ├── models.py           # DER del SRS: Paciente, Medico, Horario, Turno, ObraSocial, Especialidad, Usuario
│   ├── seed.py             # Datos iniciales y usuarios de demostración
│   ├── seguridad.py        # Token CSRF de los formularios
│   ├── auth/               # Blueprint: login, registro, logout, control por rol
│   ├── turnos/             # Blueprint: CU-01 a CU-04 (+ servicios.py con las reglas)
│   ├── pacientes/          # Blueprint: CRUD de pacientes
│   ├── ia/                 # Blueprint y servicio del modelo de IA
│   ├── api/                # Blueprint: API REST JSON
│   ├── templates/          # Plantillas Jinja2
│   └── static/css/
├── ml/train_model.py       # Entrenamiento del modelo
├── models/                 # Modelo serializado (.joblib)
└── tests/                  # Tests con pytest
```

## Cómo ejecutarlo en local

```bash
python -m venv .venv
.\.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env            # completar SECRET_KEY y SEED_PASSWORD
python run.py                     # http://127.0.0.1:5000
```

Sin `DATABASE_URL` se usa SQLite (`instance/turnos.db`). La primera vez se crean las tablas y los datos de ejemplo.

**Usuarios de demostración** (contraseña = valor de `SEED_PASSWORD`):

| Usuario | Rol | Qué ve |
|---|---|---|
| `laura` | Secretaria | Agenda completa, pacientes, alta, reprogramación y cancelación de turnos, predicción |
| `sgomez` | Médica (Dra. Silvia Gómez) | Solo su agenda y la asistencia |
| `mperez` | Médico (Dr. Martín Pérez) | Solo su agenda y la asistencia |
| `lucia` | Paciente (Lucía Fernández) | Solo sus turnos; puede pedir, reprogramar y cancelar |

También se puede crear una cuenta de paciente nueva desde `/auth/registro`.

## Tests

```bash
python -m pytest
```

24 tests cubren el login y el hash con Bcrypt, el control por rol, las reglas de turnos (horarios disponibles, superposición, reprogramación y cancelación lógica), el CRUD de pacientes, la API REST y el modelo de IA.

## Despliegue en Render

1. Subir el repositorio a GitHub.
2. En Render, **New → Blueprint** y elegir el repositorio. `render.yaml` crea:
   - el servicio web (`pip install -r requirements.txt`, inicio con `gunicorn run:app`);
   - la base **PostgreSQL** `turnos-db`, cuya URL se pasa como `DATABASE_URL`.
3. Completar la variable `SEED_PASSWORD`. `SECRET_KEY` la genera Render.

## Decisiones de diseño

- **Cancelar no borra el turno:** lo pasa a estado «cancelado», como exige RNF-06 del SRS, para conservar el historial. El horario se libera.
- **Índice único parcial** (médico + fecha + hora, sin contar cancelados): aunque dos personas confirmen el mismo horario al mismo tiempo, la base rechaza el segundo turno (CU-01, flujo 5a).
- **Reglas en una capa de servicios** (`turnos/servicios.py`): las pantallas y la API usan las mismas funciones, así no se duplican las validaciones.
- **Seguridad:**
  - contraseñas con Bcrypt;
  - secretos en variables de entorno;
  - token CSRF en los formularios;
  - cookies de sesión `HttpOnly` y `SameSite=Lax`;
  - mismo mensaje de error si falla el usuario o la contraseña;
  - protección contra redirecciones abiertas en `?next=`.
- **SQLite en desarrollo y PostgreSQL en producción** con el mismo código: solo cambia `DATABASE_URL`.
