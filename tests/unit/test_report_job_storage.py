"""Escritura del resultado de un reporte asíncrono en reports/jobs/ (J-08, punto 6)."""

from __future__ import annotations

import json
from uuid import UUID

import pytest

pytest.importorskip("pydantic")

from workers import reports  # noqa: E402

JOB = UUID("11111111-2222-3333-4444-555555555555")


class FakeS3:
    def __init__(self) -> None:
        self.puts: list[dict] = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


def test_report_object_key_is_under_reports_jobs():
    assert reports.report_object_key(JOB) == f"reports/jobs/{JOB}.json"


def test_store_report_writes_json_with_correlation_id_metadata():
    s3 = FakeS3()
    result = {"warehouse_id": "WH-001", "movements_by_type": [], "top_skus": []}

    key = reports.store_report(JOB, result, "COR-20261126-abcd1234", client=s3)

    assert key == f"reports/jobs/{JOB}.json"
    (put,) = s3.puts
    assert put["Key"] == key
    assert put["Metadata"] == {"correlation-id": "COR-20261126-abcd1234"}
    body = json.loads(put["Body"])
    assert body["job_id"] == str(JOB)
    assert body["warehouse_id"] == "WH-001"


def test_storing_the_same_job_twice_uses_the_same_key():
    s3 = FakeS3()

    reports.store_report(JOB, {"a": 1}, "COR-1", client=s3)
    reports.store_report(JOB, {"a": 1}, "COR-1", client=s3)

    assert {put["Key"] for put in s3.puts} == {f"reports/jobs/{JOB}.json"}
