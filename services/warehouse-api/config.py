import os

from dotenv import load_dotenv

load_dotenv()

# Identificador de esta bodega (texto, p. ej. "WH-001"). Sale del entorno: el
# cliente nunca lo envía. La misma imagen se levanta una vez por bodega.
WAREHOUSE_ID = os.getenv("WAREHOUSE_ID", "WH-001").strip()

# Caché Redis (Cache Aside). Sin REDIS_URL o con CACHE_ENABLED=false no se usa.
REDIS_URL = os.getenv("REDIS_URL", "")
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))
REDIS_TIMEOUT_SECONDS = float(os.getenv("REDIS_TIMEOUT_SECONDS", "0.2"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Clave que el cliente envía en el header X-API-Key. Sin ella la API no arranca.
API_KEY = os.getenv("API_KEY", "")


def validate_settings() -> None:
    if not WAREHOUSE_ID or len(WAREHOUSE_ID) > 20:
        raise RuntimeError("WAREHOUSE_ID debe tener entre 1 y 20 caracteres")
    if not API_KEY:
        raise RuntimeError("API_KEY no está configurada")
