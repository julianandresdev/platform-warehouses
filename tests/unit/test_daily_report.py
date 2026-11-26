"""Pruebas del reporte diario del batch (J-08) con HTTP y storage simulados."""

from __future__ import annotations

import urllib.error
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from batch import daily_report
from batch.daily_report import (
    CentralRegistrationError,
    build_summary,
    inventory_key,
    run_daily_report,
    summary_key,
)

DAY = date(2026, 11, 24)
ENV = {
    "WH001_API_URL": "http://wh1:8000",
    "WH002_API_URL": "http://wh2:8000",
    "WH003_API_URL": "http://wh3:8000",
    "API_KEY": "wh-key",
    "CENTRAL_API_URL": "http://central:8000",
    "CENTRAL_API_KEY": "central-key",
}


def movement(sku: str, kind: str, quantity: int, warehouse_id: str = "WH-001") -> dict:
    return {"sku": sku, "type": kind, "quantity": quantity, "warehouse_id": warehouse_id}


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.metadata: dict[str, dict] = {}

    def put_json(self, key, obj, metadata=None) -> None:
        self.objects[key] = obj
        self.metadata[key] = metadata or {}


class FakeWarehouses:
    """Responde /inventory y /movements por URL base; las bodegas en `down` fallan."""

    def __init__(self, movements: dict[str, list[dict]], down: set[str] = frozenset()) -> None:
        self.movements = movements
        self.down = down
        self.calls: list[str] = []

    def __call__(self, url: str, headers, timeout):
        self.calls.append(url)
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0]
        warehouse_id = {"wh1": "WH-001", "wh2": "WH-002", "wh3": "WH-003"}[host]
        if warehouse_id in self.down:
            raise urllib.error.URLError("connection refused")
        if parsed.path == "/inventory":
            return [{"sku": "P-001", "quantity": 10, "warehouse_id": warehouse_id}]
        query = parse_qs(parsed.query)
        page, page_size = int(query["page"][0]), int(query["page_size"][0])
        rows = self.movements.get(warehouse_id, [])
        return rows[(page - 1) * page_size : page * page_size]


class FakeCentral:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[tuple[str, dict, dict]] = []

    def __call__(self, url, headers, body, timeout):
        if self.fail:
            raise urllib.error.URLError("central caída")
        self.requests.append((url, dict(headers), body))
        return {}


CLOCK = iter(datetime(2026, 11, 25, 6, 0, s, tzinfo=timezone.utc) for s in range(100))


def run(warehouses, central=None, store=None, env=ENV):
    store = store or FakeStore()
    central = central or FakeCentral()
    summary = run_daily_report(
        DAY, env, get=warehouses, post=central, store=store, now=lambda: next(CLOCK)
    )
    return summary, store, central


def test_summary_counts_by_type_and_warehouse_and_net_change_by_sku():
    collected = {
        "WH-001": (
            [],
            [
                movement("A", "RECEIPT", 10),
                movement("A", "SHIPMENT", 4),
                movement("B", "ADJUSTMENT", -3),
            ],
        ),
        "WH-002": ([], [movement("A", "RECEIPT", 5, "WH-002")]),
    }

    summary = build_summary(DAY, collected, ["WH-003"])

    assert summary["status"] == "PARTIAL"
    assert summary["missing_warehouses"] == ["WH-003"]
    assert summary["movements_by_type_and_warehouse"] == {
        "WH-001": {"ADJUSTMENT": 1, "RECEIPT": 1, "SHIPMENT": 1},
        "WH-002": {"RECEIPT": 1},
    }
    assert summary["net_change_by_sku"] == {"A": 11, "B": -3}
    assert summary["warehouses"]["WH-003"] == {"status": "MISSING"}
    assert summary["warehouses"]["WH-001"] == {"status": "OK", "inventory_rows": 0, "movements": 3}


def test_top_5_orders_by_units_moved_then_sku_and_keeps_five():
    movements = [movement(f"S{n}", "RECEIPT", n) for n in range(1, 8)]
    movements.append(movement("S7", "SHIPMENT", 1))
    movements.append(movement("AA", "RECEIPT", 6))

    summary = build_summary(DAY, {"WH-001": ([], movements)}, [])

    top = summary["top_5_skus"]
    assert [item["sku"] for item in top] == ["S7", "AA", "S6", "S5", "S4"]
    assert top[0] == {"sku": "S7", "units_moved": 8, "movements": 2}


def test_movement_type_without_known_effect_is_counted_but_not_netted():
    summary = build_summary(DAY, {"WH-001": ([], [movement("A", "RESERVATION", 5)])}, [])

    assert summary["movements_by_type_and_warehouse"] == {"WH-001": {"RESERVATION": 1}}
    assert summary["net_change_by_sku"] == {}


def test_run_writes_objects_with_correlation_metadata_and_registers_run():
    warehouses = FakeWarehouses(
        {"WH-001": [movement("P-001", "RECEIPT", 7)], "WH-002": [movement("P-001", "SHIPMENT", 2, "WH-002")]}
    )

    summary, store, central = run(warehouses)

    assert summary["status"] == "SUCCEEDED"
    assert sorted(store.objects) == sorted(
        [
            "warehouses/WH-001/2026/11/inventory-2026-11-24.json",
            "warehouses/WH-002/2026/11/inventory-2026-11-24.json",
            "warehouses/WH-003/2026/11/inventory-2026-11-24.json",
            "reports/daily/2026-11-24/summary.json",
        ]
    )
    correlation_ids = {meta["correlation-id"] for meta in store.metadata.values()}
    assert len(correlation_ids) == 1 and correlation_ids.pop().startswith("COR-")
    ((url, headers, body),) = central.requests
    assert url == "http://central:8000/internal/batch-runs"
    assert headers["X-API-Key"] == "central-key"
    assert body["report_date"] == "2026-11-24"
    assert body["status"] == "SUCCEEDED"
    assert body["started_at"] < body["finished_at"]
    assert sorted(body["objects"]) == sorted(store.objects)
    assert len(body["run_id"]) == 36


def test_run_asks_each_warehouse_for_the_utc_day_with_its_api_key():
    warehouses = FakeWarehouses({})

    run(warehouses)

    movement_calls = [call for call in warehouses.calls if "/movements" in call]
    assert len(movement_calls) == 3
    query = parse_qs(urlparse(movement_calls[0]).query)
    assert query["from"] == ["2026-11-24T00:00:00Z"]
    assert query["to"] == ["2026-11-25T00:00:00Z"]


def test_movements_are_read_page_by_page():
    rows = [movement("P-001", "RECEIPT", 1) for _ in range(250)]
    warehouses = FakeWarehouses({"WH-001": rows})

    summary, *_ = run(warehouses)

    pages = [call for call in warehouses.calls if call.startswith("http://wh1:8000/movements")]
    assert len(pages) == 3
    assert summary["warehouses"]["WH-001"]["movements"] == 250


def test_a_down_warehouse_leaves_the_run_partial_and_is_not_written():
    warehouses = FakeWarehouses({}, down={"WH-002"})

    summary, store, central = run(warehouses)

    assert summary["status"] == "PARTIAL"
    assert summary["missing_warehouses"] == ["WH-002"]
    assert inventory_key("WH-002", DAY) not in store.objects
    assert inventory_key("WH-001", DAY) in store.objects
    assert store.objects[summary_key(DAY)]["status"] == "PARTIAL"
    assert central.requests[0][2]["status"] == "PARTIAL"


def test_a_warehouse_without_configured_url_is_missing():
    env = {key: value for key, value in ENV.items() if key != "WH003_API_URL"}

    summary, *_ = run(FakeWarehouses({}), env=env)

    assert summary["missing_warehouses"] == ["WH-003"]


def test_two_runs_of_the_same_date_write_the_same_objects_and_two_registrations():
    warehouses = FakeWarehouses({"WH-001": [movement("P-001", "RECEIPT", 7)]})
    store = FakeStore()
    central = FakeCentral()

    run(warehouses, central, store)
    first = {key: dict(value) for key, value in store.objects.items()}
    run(warehouses, central, store)

    assert store.objects == first
    assert len(central.requests) == 2
    assert central.requests[0][2]["run_id"] != central.requests[1][2]["run_id"]
    assert central.requests[0][2]["objects"] == central.requests[1][2]["objects"]
    assert store.metadata[summary_key(DAY)]["correlation-id"].startswith("COR-")


def test_central_failure_is_reported_after_the_objects_were_written():
    store = FakeStore()

    with pytest.raises(CentralRegistrationError):
        run(FakeWarehouses({}), FakeCentral(fail=True), store)

    assert summary_key(DAY) in store.objects


def test_central_url_is_required():
    env = {key: value for key, value in ENV.items() if key != "CENTRAL_API_URL"}

    with pytest.raises(RuntimeError, match="CENTRAL_API_URL"):
        run(FakeWarehouses({}), env=env)


def test_default_date_is_yesterday_in_utc(monkeypatch):
    seen = []
    monkeypatch.setattr(daily_report, "run_daily_report", lambda day, env: seen.append(day) or {})
    monkeypatch.setattr(daily_report, "configure_logging", lambda *a, **k: None)

    assert daily_report.main([], env=ENV) == 0
    assert daily_report.main(["--date", "2026-11-20"], env=ENV) == 0

    today = datetime.now(timezone.utc).date()
    assert seen[0] == date.fromordinal(today.toordinal() - 1)
    assert seen[1] == date(2026, 11, 20)
