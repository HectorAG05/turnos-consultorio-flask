"""Punto de entrada. Desarrollo: python run.py | Producción (Render): gunicorn run:app"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
