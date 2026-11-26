"""Prueba de integración de common.storage contra MinIO (S-05).

Requiere MinIO arriba y el bucket creado:

    docker compose --profile storage up -d
    S3_ENDPOINT_URL=http://localhost:9000 AWS_ACCESS_KEY_ID=minioadmin \
    AWS_SECRET_ACCESS_KEY=minioadmin python -m pytest tests/integration/test_storage.py
"""

from __future__ import annotations

import json
import os
import unittest
import uuid

from common import storage

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")


@unittest.skipUnless(S3_ENDPOINT_URL, "define S3_ENDPOINT_URL para usar MinIO")
class StorageIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = storage.get_client()
        self.prefix = f"tests/{uuid.uuid4()}/"
        self.keys: list[str] = []

    def tearDown(self) -> None:
        for key in self.keys:
            self.client.delete_object(Bucket=storage.bucket_name(), Key=key)

    def test_put_json_writes_object_with_metadata_and_reads_it_back(self) -> None:
        key = f"{self.prefix}objeto.json"
        self.keys.append(key)
        payload = {"sku": "P-001", "cantidad": 5, "nota": "año"}

        storage.put_json(key, payload, {"correlation-id": "COR-S05"})

        obj = self.client.get_object(Bucket=storage.bucket_name(), Key=key)
        self.assertEqual(json.loads(obj["Body"].read()), payload)
        self.assertEqual(obj["Metadata"]["correlation-id"], "COR-S05")
        self.assertEqual(obj["ContentType"], "application/json")

    def test_put_json_same_key_replaces_the_object(self) -> None:
        key = f"{self.prefix}repetido.json"
        self.keys.append(key)

        storage.put_json(key, {"version": 1})
        storage.put_json(key, {"version": 2})

        obj = self.client.get_object(Bucket=storage.bucket_name(), Key=key)
        self.assertEqual(json.loads(obj["Body"].read()), {"version": 2})
        self.assertEqual(storage.list(key), [key])

    def test_list_returns_only_keys_under_the_prefix(self) -> None:
        inside = [f"{self.prefix}a/1.json", f"{self.prefix}a/2.json", f"{self.prefix}b/3.json"]
        outside = f"tests/otro-{uuid.uuid4()}/4.json"
        self.keys.extend([*inside, outside])
        for key in [*inside, outside]:
            storage.put_json(key, {"key": key})

        self.assertEqual(storage.list(self.prefix), sorted(inside))
        self.assertEqual(storage.list(f"{self.prefix}a/"), sorted(inside[:2]))
        self.assertEqual(storage.list(f"{self.prefix}no-existe/"), [])


if __name__ == "__main__":
    unittest.main()
