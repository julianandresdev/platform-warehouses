"""Escenarios de carga de la Warehouse API.

Cada escenario es una clase; se elige por nombre al lanzar Locust:

    locust -f tests/load/locustfile.py --headless -u 100 -r 100 -t 2m \
        --host http://localhost:8000 --csv docs/evidencias/fase-2/cache-on ReadSameSku

Variables: API_KEY (default dev-api-key), LOAD_SKU (default P-001).
"""

import os
import random

from locust import HttpUser, between, constant, task

# La API exige X-API-Key en todo menos /health. SKU de la semilla de cada bodega.
API_KEY = os.getenv("API_KEY", "dev-api-key")
SKU = os.getenv("LOAD_SKU", "P-001")
# Espera máxima entre peticiones de ReadSameSku (segundos). 0 = sin espera (saturación).
MAX_WAIT = float(os.getenv("LOAD_WAIT", "0.05"))


class _BaseUser(HttpUser):
    abstract = True

    def on_start(self):
        self.client.headers.update({"X-API-Key": API_KEY})


class ReadSameSku(_BaseUser):
    """F2: todos los usuarios piden el mismo SKU (el caso ideal para la caché).

    LOAD_WAIT=0 quita la espera y satura el servidor; por defecto espera 0-50 ms.
    """

    wait_time = between(0, MAX_WAIT) if MAX_WAIT > 0 else constant(0)

    @task
    def consultar_inventario(self):
        with self.client.get(
            f"/inventory/{SKU}", name="GET /inventory/{sku}", catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"status {r.status_code}")


class UsuarioBodega(_BaseUser):
    """Mezcla de consultas generales (la que se usaba en la Fase 1)."""

    wait_time = between(0.05, 0.15)

    @task
    def consultar_productos(self):
        self.client.get("/products", name="GET /products")

    @task
    def consultar_inventario(self):
        self.client.get(f"/inventory/{SKU}", name="GET /inventory/{sku}")


class ReadWriteMix(_BaseUser):
    """90 % lecturas del mismo SKU y 10 % entradas, para ver el efecto de invalidar."""

    wait_time = between(0.05, 0.15)

    @task(9)
    def leer(self):
        self.client.get(f"/inventory/{SKU}", name="GET /inventory/{sku}")

    @task(1)
    def recibir(self):
        self.client.post(
            "/inventory/movements",
            json={"sku": SKU, "type": "RECEIPT", "quantity": random.randint(1, 3), "reference": "LOAD"},
            name="POST /inventory/movements",
        )
