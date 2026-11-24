"""Entrena y guarda el modelo de predicción de ausentismo.

Modelo: regresión logística (scikit-learn) que estima la probabilidad de que un
paciente NO se presente a su turno. Responde al propósito del SRS: reducir el
ausentismo del consultorio.

Como el consultorio todavía no tiene historial real, se genera un dataset
SINTÉTICO con reglas plausibles (documentadas abajo) y una semilla fija para que
el resultado sea reproducible. Con datos reales solo hay que reemplazar el CSV.

Uso:  python ml/train_model.py
Salida: ml/data/turnos_historicos.csv y models/modelo_ausentismo.joblib
"""
import csv
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DATASET = RAIZ / "ml" / "data" / "turnos_historicos.csv"
RUTA_MODELO = RAIZ / "models" / "modelo_ausentismo.joblib"

# Variables de entrada (el mismo orden se usa al predecir en la app)
FEATURES = ["dias_anticipacion", "hora", "tiene_obra_social", "ausencias_previas"]
SEMILLA = 42
CANTIDAD_TURNOS = 3000


def generar_dataset(cantidad=CANTIDAD_TURNOS, semilla=SEMILLA):
    """Genera turnos históricos sintéticos.

    Reglas usadas para simular el ausentismo (a mayor valor, más probable que falte):
      - más días de anticipación al pedir el turno (el paciente se olvida),
      - horarios más tarde en el día,
      - ausencias previas del paciente,
      - no tener obra social baja levemente el compromiso con el turno.
    """
    rng = np.random.default_rng(semilla)
    dias = rng.integers(0, 61, cantidad)
    hora = rng.integers(8, 20, cantidad)
    tiene_obra_social = rng.binomial(1, 0.7, cantidad)
    ausencias = np.clip(rng.poisson(0.6, cantidad), 0, 6)

    z = -2.6 + 0.045 * dias + 0.09 * (hora - 8) + 0.75 * ausencias - 0.55 * tiene_obra_social
    probabilidad = 1 / (1 + np.exp(-z))
    ausente = rng.binomial(1, probabilidad)

    X = np.column_stack([dias, hora, tiene_obra_social, ausencias]).astype(float)
    return X, ausente


def guardar_csv(X, y):
    RUTA_DATASET.parent.mkdir(parents=True, exist_ok=True)
    with RUTA_DATASET.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(FEATURES + ["ausente"])
        for fila, etiqueta in zip(X, y):
            escritor.writerow([int(v) for v in fila] + [int(etiqueta)])


def entrenar(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=SEMILLA, stratify=y
    )
    # Pipeline: escalado + regresión logística en un solo objeto serializable
    pipeline = Pipeline(
        [
            ("escalado", StandardScaler()),
            ("regresion_logistica", LogisticRegression(max_iter=1000)),
        ]
    )
    pipeline.fit(X_train, y_train)

    predicciones = pipeline.predict(X_test)
    probabilidades = pipeline.predict_proba(X_test)[:, 1]
    metricas = {
        "accuracy": round(float(accuracy_score(y_test, predicciones)), 3),
        "roc_auc": round(float(roc_auc_score(y_test, probabilidades)), 3),
        "muestras_entrenamiento": int(len(y_train)),
        "muestras_prueba": int(len(y_test)),
        "tasa_ausentismo": round(float(y.mean()), 3),
    }
    print(classification_report(y_test, predicciones, target_names=["asiste", "ausente"]))
    return pipeline, metricas


def main():
    X, y = generar_dataset()
    guardar_csv(X, y)
    modelo, metricas = entrenar(X, y)

    RUTA_MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "modelo": modelo,
            "features": FEATURES,
            "metricas": metricas,
            "version_sklearn": sklearn.__version__,
            "datos": "Dataset sintético generado por ml/train_model.py (semilla 42)",
        },
        RUTA_MODELO,
    )
    print("Métricas:", metricas)
    print(f"Modelo guardado en {RUTA_MODELO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
