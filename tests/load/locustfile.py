
from locust import HttpUser, task, between


class UsuarioBodega(HttpUser):
    wait_time = between(0.05, 0.15)

    @task
    def consultar_productos(self):
        self.client.get("/products", name="GET /products")

    @task
    def consultar_inventario(self):
        self.client.get("/inventory/1", name="GET /inventory/1")
