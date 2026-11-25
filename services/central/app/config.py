import os

# Identificación del servicio
SERVICE_NAME = "central-api"

# Configuración de registros
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Clave para autenticar las solicitudes HTTP
API_KEY = os.getenv("API_KEY", "")

# Conexión con RabbitMQ
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")

# Direcciones de las APIs de las bodegas
# Se utilizarán posteriormente en la Fase 7
WAREHOUSE_URLS = os.getenv("WAREHOUSE_URLS", "")


def validate_settings():
    """Verifica las variables obligatorias."""

    if not API_KEY:
        raise RuntimeError(
            "API_KEY no está configurada"
        )
