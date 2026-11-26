"""Pruebas de la Lambda report-validator (S-08) con S3 y la central simulados."""

from __future__ import annotations

import hashlib
import io
import json
import socketserver
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import handler

KEY = "reports/daily/2026-11-25/summary.json"


def daily_summary(**overrides) -> dict:
    report = {
        "report_date": "2026-11-25",
        "status": "SUCCEEDED",
        "missing_warehouses": [],
        "warehouses": {
            "WH-001": {"status": "OK", "inventory_rows": 10, "movements": 12},
            "WH-002": {"status": "OK", "inventory_rows": 10, "movements": 11},
            "WH-003": {"status": "MISSING"},
        },
        "movements_by_type_and_warehouse": {},
        "net_change_by_sku": {},
        "top_5_skus": [],
    }
    report.update(overrides)
    return report


def encode(report) -> bytes:
    return json.dumps(report).encode()


class FakeS3:
    def __init__(self, objects: dict[str, tuple[bytes, dict]]) -> None:
        self.objects = objects
        self.puts: list[dict] = []

    def get_object(self, Bucket, Key):
        body, metadata = self.objects[Key]
        return {"Body": io.BytesIO(body), "Metadata": metadata}

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


class FakeCentral:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self.error = error

    def __call__(self, url, api_key, correlation_id, body):
        if self.error:
            raise self.error
        self.calls.append((url, api_key, correlation_id, body))


def process(key, raw, metadata=None, central=None):
    s3 = FakeS3({key: (raw, metadata or {})})
    central = central or FakeCentral()
    result = handler.process_object(
        s3, "warehouse-platform", key,
        central_url="http://central:8000", api_key="central-key", post=central,
    )
    return result, s3, central


# -------------------------
# VALIDACIÓN
# -------------------------

def test_valid_daily_summary_counts_the_movements_of_the_warehouses():
    status, reason, records = handler.validate_report(KEY, encode(daily_summary()))

    assert (status, reason, records) == ("VALID", None, 23)


@pytest.mark.parametrize(
    "report, reason",
    [
        ({"report_date": "2026-11-25"}, "Faltan campos obligatorios"),
        (daily_summary(status="OTRO"), "status desconocido"),
        (daily_summary(report_date="25/11/2026"), "report_date no es una fecha"),
        (daily_summary(report_date="2026-11-24"), "no coincide con la fecha de la llave"),
        (daily_summary(warehouses=[]), "warehouses debe ser un objeto"),
        (daily_summary(warehouses={"WH-001": {"movements": -1}}), "movements debe ser un entero"),
        (daily_summary(warehouses={"WH-001": {"movements": True}}), "movements debe ser un entero"),
        ([1, 2], "debe ser un objeto JSON"),
    ],
)
def test_invalid_daily_summary_explains_why(report, reason):
    status, message, records = handler.validate_report(KEY, encode(report))

    assert status == "INVALID"
    assert reason in message
    assert records is None


def test_not_json_is_invalid():
    status, message, _ = handler.validate_report(KEY, b"\xff\xfe no es json")

    assert status == "INVALID"
    assert "JSON" in message


def test_other_reports_only_need_to_be_a_json_object():
    assert handler.validate_report("reports/jobs/abc.json", b'{"job_id": "abc"}') == ("VALID", None, None)
    assert handler.validate_report("reports/jobs/abc.json", b"[]")[0] == "INVALID"


def test_the_summary_written_by_the_batch_is_valid_for_the_lambda():
    from datetime import date

    from batch.daily_report import build_summary, summary_key

    day = date(2026, 11, 25)
    collected = {
        "WH-001": ([{"sku": "P-001"}], [{"sku": "P-001", "type": "RECEIPT", "quantity": 4}]),
        "WH-002": ([], []),
    }
    summary = build_summary(day, collected, ["WH-003"])

    status, reason, records = handler.validate_report(summary_key(day), encode(summary))

    assert (status, reason, records) == ("VALID", None, 1)


# -------------------------
# PROCESO DE UN OBJETO
# -------------------------

def test_valid_report_writes_metadata_and_registers_in_central_with_correlation_id():
    raw = encode(daily_summary())

    result, s3, central = process(KEY, raw, {"correlation-id": "COR-20261125-aaaa1111"})

    assert result["status"] == "VALID"
    assert result["size"] == len(raw)
    assert result["checksum"] == hashlib.sha256(raw).hexdigest()
    assert result["record_count"] == 23
    (put,) = s3.puts
    assert put["Key"] == "metadata/reports/daily/2026-11-25/summary.json"
    assert put["Metadata"] == {"correlation-id": "COR-20261125-aaaa1111"}
    assert json.loads(put["Body"])["checksum"] == result["checksum"]
    ((url, api_key, correlation_id, body),) = central.calls
    assert url == "http://central:8000/internal/reports"
    assert api_key == "central-key"
    assert correlation_id == "COR-20261125-aaaa1111"
    assert body["object_key"] == KEY
    assert body["status"] == "VALID"
    assert body["size"] == len(raw) and body["checksum"] == result["checksum"]
    assert body["metadata"]["record_count"] == 23
    assert body["metadata"]["metadata_key"] == put["Key"]


def test_invalid_report_is_still_written_and_registered_as_invalid():
    result, s3, central = process(KEY, encode({"report_date": "2026-11-25"}), {"correlation-id": "COR-1"})

    assert result["status"] == "INVALID"
    assert "Faltan campos" in result["reason"]
    assert len(s3.puts) == 1
    assert central.calls[0][3]["status"] == "INVALID"
    assert central.calls[0][3]["metadata"]["reason"] == result["reason"]


def test_object_without_correlation_id_metadata_does_not_invent_one(caplog):
    caplog.set_level("INFO")

    result, s3, central = process(KEY, encode(daily_summary()))

    assert result["correlation_id"] is None
    assert s3.puts[0]["Metadata"] == {}
    assert central.calls[0][2] is None


def test_the_log_line_carries_the_correlation_id(caplog):
    caplog.set_level("INFO")

    process(KEY, encode(daily_summary()), {"correlation-id": "COR-20261125-bbbb2222"})

    lines = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    validated = [line for line in lines if line["event"] == "report_validated"]
    assert validated[0]["correlation_id"] == "COR-20261125-bbbb2222"
    assert validated[0]["object_key"] == KEY


def test_central_failure_propagates_so_that_s3_retries():
    with pytest.raises(urllib.error.URLError):
        process(KEY, encode(daily_summary()), central=FakeCentral(urllib.error.URLError("caída")))


# -------------------------
# LAMBDA_HANDLER
# -------------------------

def s3_event(*keys: str) -> dict:
    return {
        "Records": [
            {"eventSource": "aws:s3", "s3": {"bucket": {"name": "warehouse-platform"}, "object": {"key": key}}}
            for key in keys
        ]
    }


def test_handler_requires_the_central_configuration(monkeypatch):
    monkeypatch.delenv("CENTRAL_API_URL", raising=False)
    monkeypatch.delenv("CENTRAL_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="CENTRAL_API_URL"):
        handler.lambda_handler(s3_event(KEY), None)


def test_handler_ignores_its_own_output_and_non_reports(monkeypatch):
    monkeypatch.setenv("CENTRAL_API_URL", "http://central:8000")
    monkeypatch.setenv("CENTRAL_API_KEY", "k")
    monkeypatch.setattr(handler.boto3, "client", lambda *a, **k: pytest.fail("no debe leer S3"))

    result = handler.lambda_handler(
        s3_event(
            "metadata/reports/daily/2026-11-25/summary.json",
            "warehouses/WH-001/2026/11/inventory-2026-11-25.json",
            "reports/daily/2026-11-25/notas.txt",
        ),
        None,
    )

    assert result == {"processed": 0, "invalid": 0, "ignored": 3}


def test_handler_decodes_the_key_and_counts_valid_and_invalid(monkeypatch):
    monkeypatch.setenv("CENTRAL_API_URL", "http://central:8000/")
    monkeypatch.setenv("CENTRAL_API_KEY", "k")
    objects = {
        KEY: (encode(daily_summary()), {}),
        "reports/jobs/un job.json": (b"[]", {}),
    }
    fake = FakeS3(objects)
    calls = []
    monkeypatch.setattr(handler.boto3, "client", lambda *a, **k: fake)
    monkeypatch.setattr(handler, "post_report", lambda *args: calls.append(args))

    result = handler.lambda_handler(s3_event(KEY, "reports/jobs/un+job.json"), None)

    assert result == {"processed": 1, "invalid": 1, "ignored": 0}
    assert calls[0][0] == "http://central:8000/internal/reports"


# -------------------------
# POST A LA CENTRAL (HTTP real en local)
# -------------------------

class _Central(BaseHTTPRequestHandler):
    received: list[dict] = []
    status = 201

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        headers = {name.lower(): value for name, value in self.headers.items()}
        type(self).received.append({"path": self.path, "headers": headers, "body": body})
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *args):
        pass


class _LocalServer(HTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind hace un getfqdn() que tarda ~35 s en algunas redes.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


@pytest.fixture
def central_server():
    _Central.received = []
    _Central.status = 201
    server = _LocalServer(("127.0.0.1", 0), _Central)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", _Central
    server.shutdown()


def test_post_report_sends_api_key_and_correlation_header(central_server):
    url, central = central_server

    handler.post_report(f"{url}/internal/reports", "central-key", "COR-9", {"object_key": KEY})

    (request,) = central.received
    assert request["path"] == "/internal/reports"
    assert request["headers"]["x-api-key"] == "central-key"
    assert request["headers"]["x-correlation-id"] == "COR-9"
    assert request["body"] == {"object_key": KEY}


def test_post_report_treats_409_as_already_registered(central_server):
    url, central = central_server
    central.status = 409

    handler.post_report(f"{url}/internal/reports", "k", None, {"object_key": KEY})


def test_post_report_raises_on_other_http_errors(central_server):
    url, central = central_server
    central.status = 401

    with pytest.raises(urllib.error.HTTPError):
        handler.post_report(f"{url}/internal/reports", "mala", None, {"object_key": KEY})
