import sys
from pathlib import Path

import fakeredis
import pytest
import redis

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "warehouse-api"))

import cache  # noqa: E402
import config  # noqa: E402

DATO = {"sku": "P-001", "quantity": 100}


@pytest.fixture
def fake(monkeypatch):
    server = fakeredis.FakeRedis()
    monkeypatch.setattr(config, "REDIS_URL", "redis://fake")
    monkeypatch.setattr(config, "CACHE_ENABLED", True)
    monkeypatch.setattr(config, "WAREHOUSE_ID", "WH-001")
    monkeypatch.setattr(cache, "_client", server)
    return server


def valor(counter):
    return counter._value.get()


def test_llave_incluye_bodega_y_sku(fake):
    assert cache.inventory_key("P-001") == "warehouse:WH-001:inventory:P-001"


def test_miss_luego_hit(fake):
    hits, misses = valor(cache.cache_hits_total), valor(cache.cache_misses_total)

    assert cache.get_inventory("P-001") == (None, cache.MISS)
    cache.set_inventory("P-001", DATO)
    assert cache.get_inventory("P-001") == (DATO, cache.HIT)

    assert valor(cache.cache_misses_total) == misses + 1
    assert valor(cache.cache_hits_total) == hits + 1


def test_set_aplica_ttl(fake):
    cache.set_inventory("P-001", DATO)
    assert 0 < fake.ttl(cache.inventory_key("P-001")) <= 30


def test_invalidacion_borra_la_llave(fake):
    cache.set_inventory("P-001", DATO)
    cache.invalidate_inventory("P-001")
    assert cache.get_inventory("P-001") == (None, cache.MISS)


def test_cache_apagada_es_bypass(fake, monkeypatch):
    monkeypatch.setattr(config, "CACHE_ENABLED", False)
    cache.set_inventory("P-001", DATO)
    assert fake.keys("*") == []
    assert cache.get_inventory("P-001") == (None, cache.BYPASS)


class RedisCaido:
    def get(self, *a, **k):
        raise redis.ConnectionError("caído")

    set = delete = get


def test_redis_caido_no_lanza(fake, monkeypatch, caplog):
    monkeypatch.setattr(cache, "_client", RedisCaido())
    with caplog.at_level("WARNING", logger="warehouse-api"):
        assert cache.get_inventory("P-001") == (None, cache.BYPASS)
        cache.set_inventory("P-001", DATO)
        cache.invalidate_inventory("P-001")
    assert [r.getMessage() for r in caplog.records].count("cache_unavailable") == 3


def test_redis_real_inalcanzable_responde_rapido(monkeypatch):
    # Cliente real contra un puerto cerrado: debe fallar en milisegundos, no colgarse.
    import time

    monkeypatch.setattr(config, "REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(config, "CACHE_ENABLED", True)
    monkeypatch.setattr(cache, "_client", None)
    t = time.perf_counter()
    assert cache.get_inventory("P-001") == (None, cache.BYPASS)
    assert time.perf_counter() - t < 1
