import os

from locust import HttpUser, task, between

# La API exige X-API-Key en todo menos /health. SKU de la semilla de cada bodega.
API_KEY = os.getenv("API_KEY", "dev-api-key")
SKU = os.getenv("LOAD_SKU", "P-001")


class UsuarioBodega(HttpUser):
    wait_time = between(0.05, 0.15)

    def on_start(self):
        self.client.headers.update({"X-API-Key": API_KEY})

    @task
    def consultar_productos(self):
        self.client.get("/products", name="GET /products")

    @task
    def consultar_inventario(self):
        self.client.get(f"/inventory/{SKU}", name="GET /inventory/{sku}")
