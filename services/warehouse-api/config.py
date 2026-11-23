import os

from dotenv import load_dotenv

load_dotenv()

# Identificador de esta bodega (texto, p. ej. "WH-001"). Sale del entorno: el
# cliente nunca lo envía. La misma imagen se levanta una vez por bodega.
WAREHOUSE_ID = os.getenv("WAREHOUSE_ID", "WH-001").strip()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Clave que el cliente envía en el header X-API-Key. Sin ella la API no arranca.
API_KEY = os.getenv("API_KEY", "")


def validate_settings() -> None:
    if not WAREHOUSE_ID or len(WAREHOUSE_ID) > 20:
        raise RuntimeError("WAREHOUSE_ID debe tener entre 1 y 20 caracteres")
    if not API_KEY:
        raise RuntimeError("API_KEY no está configurada")
