import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración general de la aplicación Aulas Inteligentes con IA."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    DEBUG = os.environ.get("FLASK_ENV", "development") == "development"
    PORT = int(os.environ.get("PORT", 5000))

    APP_NAME = "Aulas Inteligentes con IA"
    APP_TAGLINE = "Powered by Claude"
