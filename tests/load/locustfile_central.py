import os

from locust import HttpUser, between, task


class GlobalInventoryUser(HttpUser):
    wait_time = between(0.05, 0.15)

    @task
    def inventory(self):
        mode = os.getenv("LOAD_MODE", "cqrs")
        sku = os.getenv("LOAD_SKU", "P-001")
        key = os.getenv("CENTRAL_API_KEY", "dev-central-key")

        self.client.get(
            f"/global/inventory/{sku}",
            params={"mode": mode},
            headers={"X-API-Key": key},
            name=f"GET global inventory [{mode}]",
        )
