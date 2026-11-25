"""Reporte diario del batch (J-08, issue #12).

    python -m batch.daily_report --date YYYY-MM-DD      # por defecto, ayer (UTC)

Para cada bodega lee su API (nunca su base): ``GET /inventory`` y
``GET /movements`` del día. Si una no responde queda como faltante y la
ejecución termina ``PARTIAL``. Con lo recibido escribe en el bucket:

- ``warehouses/WH-00X/YYYY/MM/inventory-YYYY-MM-DD.json`` (una por bodega que respondió)
- ``reports/daily/YYYY-MM-DD/summary.json``

Las llaves dependen solo de la fecha, así que repetir la ejecución de un día
reemplaza los mismos objetos; cada ejecución se registra en la central con su
propio ``run_id`` (``POST /internal/batch-runs``). Cada objeto lleva el metadato
``correlation-id`` de la ejecución.

El día va de 00:00 a 24:00 UTC porque ``created_at`` se guarda en UTC.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Mapping

from common import storage
from common.correlation import (
    HEADER_NAME as CORRELATION_HEADER,
    generate_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from common.logging import configure_logging

logger = logging.getLogger("batch")

WAREHOUSES = ("WH-001", "WH-002", "WH-003")
PAGE_SIZE = 100
MAX_PAGES = 10_000
TOP_N = 5
SUCCEEDED = "SUCCEEDED"
PARTIAL = "PARTIAL"
DEFAULT_TIMEOUT_SECONDS = 10.0


class WarehouseUnavailable(Exception):
    """La API de la bodega no respondió o devolvió algo que no es el contrato."""


class CentralRegistrationError(Exception):
    """La central no registró la ejecución."""


# -------------------------
# HTTP (inyectable en pruebas)
# -------------------------

def http_get_json(url: str, headers: Mapping[str, str], timeout: float) -> Any:
    request = urllib.request.Request(url, headers={**headers, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def http_post_json(url: str, headers: Mapping[str, str], body: Any, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


# -------------------------
# LECTURA DE BODEGAS
# -------------------------

def day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch_warehouse(
    base_url: str,
    day: date,
    headers: Mapping[str, str],
    *,
    get: Callable[..., Any] = http_get_json,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[list[dict], list[dict]]:
    """Inventario y movimientos del día de una bodega; todo o nada."""

    base = base_url.rstrip("/")
    start, end = day_range(day)
    try:
        inventory = get(f"{base}/inventory", headers, timeout)
        movements: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            query = urllib.parse.urlencode(
                {"from": _iso_z(start), "to": _iso_z(end), "page": page, "page_size": PAGE_SIZE}
            )
            chunk = get(f"{base}/movements?{query}", headers, timeout)
            if not isinstance(chunk, list):
                raise WarehouseUnavailable("GET /movements no devolvió una lista")
            movements.extend(chunk)
            if len(chunk) < PAGE_SIZE:
                break
        else:
            raise WarehouseUnavailable("se superó el máximo de páginas de movimientos")
    except WarehouseUnavailable:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise WarehouseUnavailable(str(exc) or exc.__class__.__name__) from exc

    if not isinstance(inventory, list):
        raise WarehouseUnavailable("GET /inventory no devolvió una lista")
    return inventory, movements


# -------------------------
# RESUMEN
# -------------------------

def _net_effect(movement: Mapping[str, Any]) -> int | None:
    """Efecto del movimiento sobre la cantidad; None si el tipo no se conoce.

    RECEIPT suma, SHIPMENT resta y ADJUSTMENT ya guarda la diferencia con signo.
    """

    quantity = int(movement["quantity"])
    kind = movement["type"]
    if kind == "RECEIPT":
        return quantity
    if kind == "SHIPMENT":
        return -quantity
    if kind == "ADJUSTMENT":
        return quantity
    return None


def build_summary(
    day: date,
    collected: Mapping[str, tuple[list[dict], list[dict]]],
    missing: list[str],
) -> dict[str, Any]:
    by_type: dict[str, dict[str, int]] = {}
    net_by_sku: Counter[str] = Counter()
    units_by_sku: Counter[str] = Counter()
    movements_by_sku: Counter[str] = Counter()
    warehouses: dict[str, dict[str, Any]] = {}

    for warehouse_id in WAREHOUSES:
        if warehouse_id not in collected:
            warehouses[warehouse_id] = {"status": "MISSING"}
            continue
        inventory, movements = collected[warehouse_id]
        counts: Counter[str] = Counter()
        for movement in movements:
            counts[movement["type"]] += 1
            sku = movement["sku"]
            units_by_sku[sku] += abs(int(movement["quantity"]))
            movements_by_sku[sku] += 1
            effect = _net_effect(movement)
            if effect is None:
                logger.warning(
                    "movement_type_without_net_effect",
                    extra={"warehouse_id": warehouse_id, "type": movement["type"]},
                )
            else:
                net_by_sku[sku] += effect
        by_type[warehouse_id] = dict(sorted(counts.items()))
        warehouses[warehouse_id] = {
            "status": "OK",
            "inventory_rows": len(inventory),
            "movements": len(movements),
        }

    top = sorted(units_by_sku.items(), key=lambda item: (-item[1], item[0]))[:TOP_N]
    return {
        "report_date": day.isoformat(),
        "status": PARTIAL if missing else SUCCEEDED,
        "missing_warehouses": sorted(missing),
        "warehouses": warehouses,
        "movements_by_type_and_warehouse": by_type,
        "net_change_by_sku": dict(sorted(net_by_sku.items())),
        "top_5_skus": [
            {"sku": sku, "units_moved": units, "movements": movements_by_sku[sku]}
            for sku, units in top
        ],
    }


def inventory_key(warehouse_id: str, day: date) -> str:
    return f"warehouses/{warehouse_id}/{day:%Y}/{day:%m}/inventory-{day.isoformat()}.json"


def summary_key(day: date) -> str:
    return f"reports/daily/{day.isoformat()}/summary.json"


# -------------------------
# EJECUCIÓN
# -------------------------

def run_daily_report(
    day: date,
    env: Mapping[str, str],
    *,
    get: Callable[..., Any] = http_get_json,
    post: Callable[..., Any] = http_post_json,
    store: Any = storage,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Genera el reporte de ``day`` y lo registra en la central. Devuelve el resumen."""

    central_url = env.get("CENTRAL_API_URL", "").rstrip("/")
    if not central_url:
        raise RuntimeError("CENTRAL_API_URL es obligatoria: la ejecución se registra en la central")

    timeout = float(env.get("HTTP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    correlation_id = generate_correlation_id()
    token = set_correlation_id(correlation_id)
    started_at = now()
    try:
        warehouse_headers = {
            "X-API-Key": env.get("API_KEY", ""),
            CORRELATION_HEADER: correlation_id,
        }
        metadata = {"correlation-id": correlation_id}
        collected: dict[str, tuple[list[dict], list[dict]]] = {}
        missing: list[str] = []
        objects: list[str] = []

        for warehouse_id in WAREHOUSES:
            base_url = env.get(f"{warehouse_id.replace('-', '')}_API_URL", "")
            try:
                if not base_url:
                    raise WarehouseUnavailable("URL de la API no configurada")
                collected[warehouse_id] = fetch_warehouse(
                    base_url, day, warehouse_headers, get=get, timeout=timeout
                )
            except WarehouseUnavailable as exc:
                missing.append(warehouse_id)
                logger.error(
                    "warehouse_unavailable",
                    extra={"warehouse_id": warehouse_id, "error": str(exc)},
                )
                continue

            key = inventory_key(warehouse_id, day)
            store.put_json(
                key,
                {
                    "warehouse_id": warehouse_id,
                    "report_date": day.isoformat(),
                    "inventory": collected[warehouse_id][0],
                },
                metadata,
            )
            objects.append(key)

        summary = build_summary(day, collected, missing)
        key = summary_key(day)
        store.put_json(key, summary, metadata)
        objects.append(key)

        run = {
            "run_id": str(uuid.uuid4()),
            "report_date": day.isoformat(),
            "status": summary["status"],
            "started_at": _iso_z(started_at),
            "finished_at": _iso_z(now()),
            "objects": objects,
        }
        central_headers = {
            "X-API-Key": env.get("CENTRAL_API_KEY", ""),
            CORRELATION_HEADER: correlation_id,
        }
        try:
            post(f"{central_url}/internal/batch-runs", central_headers, run, timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise CentralRegistrationError(str(exc) or exc.__class__.__name__) from exc

        logger.info(
            "daily_report_finished",
            extra={"run_id": run["run_id"], "report_date": run["report_date"],
                   "status": run["status"], "missing_warehouses": missing},
        )
        return summary
    finally:
        reset_correlation_id(token)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m batch.daily_report")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="día del reporte, YYYY-MM-DD (por defecto, ayer en UTC)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    configure_logging("batch", None, env.get("LOG_LEVEL", "INFO"))
    args = parse_args(argv)
    day = args.date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    try:
        summary = run_daily_report(day, env)
    except (RuntimeError, CentralRegistrationError) as exc:
        logger.error("daily_report_failed", extra={"error": str(exc)})
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
