"""Cache Aside sobre Redis para GET /inventory/{sku} (ADR-0008).

Redis nunca es fuente de verdad: cualquier fallo se registra y se responde desde
PostgreSQL. Las escrituras no dependen de Redis (la invalidación no lanza).
"""

import json
import logging

import redis
from prometheus_client import Counter

import config

logger = logging.getLogger("warehouse-api")

cache_hits_total = Counter("cache_hits_total", "Lecturas de inventario servidas desde Redis")
cache_misses_total = Counter("cache_misses_total", "Lecturas de inventario que fueron a PostgreSQL")

HIT, MISS, BYPASS = "HIT", "MISS", "BYPASS"

_client: redis.Redis | None = None


def enabled() -> bool:
    return config.CACHE_ENABLED and bool(config.REDIS_URL)


def _redis() -> redis.Redis:
    # Cliente con pool y timeouts cortos: una caída de Redis no debe colgar la API.
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            config.REDIS_URL,
            socket_timeout=config.REDIS_TIMEOUT_SECONDS,
            socket_connect_timeout=config.REDIS_TIMEOUT_SECONDS,
            max_connections=20,
        )
    return _client


def inventory_key(sku: str) -> str:
    return f"warehouse:{config.WAREHOUSE_ID}:inventory:{sku}"


def get_inventory(sku: str):
    """Devuelve (dato | None, estado). Estado: HIT, MISS o BYPASS (caché apagada o caída)."""
    if not enabled():
        return None, BYPASS
    try:
        raw = _redis().get(inventory_key(sku))
    except redis.RedisError:
        logger.warning("cache_unavailable", extra={"operation": "get", "sku": sku})
        return None, BYPASS
    if raw is None:
        cache_misses_total.inc()
        return None, MISS
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("el valor cacheado no es un objeto")
    except ValueError:
        # Valor corrupto o de otro formato: se descarta y se lee de PostgreSQL.
        logger.warning("cache_corrupt", extra={"sku": sku})
        invalidate_inventory(sku)
        return None, BYPASS
    cache_hits_total.inc()
    return data, HIT


def set_inventory(sku: str, data: dict) -> None:
    if not enabled():
        return
    try:
        _redis().set(inventory_key(sku), json.dumps(data), ex=config.CACHE_TTL_SECONDS)
    except redis.RedisError:
        logger.warning("cache_unavailable", extra={"operation": "set", "sku": sku})


def invalidate_inventory(sku: str, *, raise_on_error: bool = False) -> None:
    """Borra la llave. Se llama DESPUÉS del commit; nunca lanza."""
    if not enabled():
        return
    try:
        _redis().delete(inventory_key(sku))
    except redis.RedisError:
        # El TTL de 30 s acota cuánto puede durar un dato viejo.
        logger.warning("cache_unavailable", extra={"operation": "delete", "sku": sku})
        if raise_on_error:
            raise
