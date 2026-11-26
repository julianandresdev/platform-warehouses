"""Prueba de integración de la Lambda report-validator contra MinIO (S-08).

Sube un reporte, arma el evento de S3 que recibiría la Lambda y la invoca como lo
haría AWS. La central es un servidor HTTP local. Requiere MinIO con el bucket:

    docker compose --profile storage up -d minio minio-init
    S3_ENDPOINT_URL=http://localhost:9000 AWS_ACCESS_KEY_ID=minioadmin \
    AWS_SECRET_ACCESS_KEY=minioadmin python -m pytest tests/integration/test_report_validator_minio.py
"""

from __future__ import annotations

import hashlib
import json
import os
import socketserver
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from common import storage

pytestmark = pytest.mark.skipif(
    not os.getenv("S3_ENDPOINT_URL"), reason="define S3_ENDPOINT_URL para usar MinIO"
)

DAY = "2001-01-01"  # una fecha que ningún batch real usa


class _Central(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        headers = {name.lower(): value for name, value in self.headers.items()}
        type(self).received.append({"path": self.path, "headers": headers, "body": body})
        self.send_response(201)
        self.end_headers()

    def log_message(self, *args):
        pass


class _LocalServer(HTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


@pytest.fixture
def central(monkeypatch):
    _Central.received = []
    server = _LocalServer(("127.0.0.1", 0), _Central)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("CENTRAL_API_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("CENTRAL_API_KEY", "central-key")
    yield _Central
    server.shutdown()


@pytest.fixture
def bucket():
    client = storage.get_client()
    created: list[str] = []
    yield client, created
    for key in created:
        client.delete_object(Bucket=storage.bucket_name(), Key=key)


def s3_event(key: str) -> dict:
    return {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {"bucket": {"name": storage.bucket_name()}, "object": {"key": key}},
            }
        ]
    }


def summary(**overrides) -> dict:
    report = {
        "report_date": DAY,
        "status": "SUCCEEDED",
        "missing_warehouses": [],
        "warehouses": {"WH-001": {"status": "OK", "inventory_rows": 3, "movements": 5}},
        "movements_by_type_and_warehouse": {"WH-001": {"RECEIPT": 5}},
        "net_change_by_sku": {"P-001": 5},
        "top_5_skus": [],
    }
    report.update(overrides)
    return report


def test_uploaded_report_gets_metadata_and_is_registered_in_the_central(central, bucket):
    import handler

    client, created = bucket
    key = f"reports/daily/{DAY}/summary.json"
    metadata_key = f"metadata/{key}"
    created.extend([key, metadata_key])
    storage.put_json(key, summary(), {"correlation-id": "COR-20010101-s08test"})

    result = handler.lambda_handler(s3_event(key), None)

    assert result == {"processed": 1, "invalid": 0, "ignored": 0}
    raw = client.get_object(Bucket=storage.bucket_name(), Key=key)["Body"].read()
    written = client.get_object(Bucket=storage.bucket_name(), Key=metadata_key)
    metadata = json.loads(written["Body"].read())
    assert metadata["status"] == "VALID"
    assert metadata["size"] == len(raw)
    assert metadata["checksum"] == hashlib.sha256(raw).hexdigest()
    assert metadata["record_count"] == 5
    assert written["Metadata"]["correlation-id"] == "COR-20010101-s08test"
    (request,) = central.received
    assert request["path"] == "/internal/reports"
    assert request["headers"]["x-api-key"] == "central-key"
    assert request["headers"]["x-correlation-id"] == "COR-20010101-s08test"
    assert request["body"]["object_key"] == key
    assert request["body"]["checksum"] == metadata["checksum"]


def test_invalid_report_is_registered_as_invalid(central, bucket):
    import handler

    client, created = bucket
    key = f"reports/daily/{DAY}/summary.json"
    created.extend([key, f"metadata/{key}"])
    storage.put_json(key, {"report_date": DAY}, {"correlation-id": "COR-20010101-s08bad"})

    result = handler.lambda_handler(s3_event(key), None)

    assert result == {"processed": 0, "invalid": 1, "ignored": 0}
    assert central.received[0]["body"]["status"] == "INVALID"
    assert "Faltan campos" in central.received[0]["body"]["metadata"]["reason"]


def test_the_metadata_object_does_not_trigger_the_lambda_again(central, bucket):
    import handler

    _, created = bucket
    key = f"reports/daily/{DAY}/summary.json"
    created.extend([key, f"metadata/{key}"])
    storage.put_json(key, summary())
    handler.lambda_handler(s3_event(key), None)

    result = handler.lambda_handler(s3_event(f"metadata/{key}"), None)

    assert result == {"processed": 0, "invalid": 0, "ignored": 1}
    assert len(central.received) == 1
