"""Lambda report-validator (S-08, issue #29).

S3 la invoca cuando se crea un ``reports/**/*.json``. Por cada objeto:

1. Lo lee y calcula su tamaño y su SHA-256.
2. Valida los campos obligatorios y cuenta sus registros.
3. Escribe el resultado en ``metadata/<llave original>`` (fuera de ``reports/``,
   así la propia Lambda no se dispara en bucle).
4. Lo registra en la central con ``POST /internal/reports`` y ``X-API-Key``.
   Un reporte inválido también se registra, con estado ``INVALID``.
5. Registra en el log el ``correlation-id`` que trae el metadato del objeto.

Un fallo de S3 o de la central se propaga: S3 reintenta la invocación.
Variables de entorno: ``CENTRAL_API_URL`` y ``CENTRAL_API_KEY`` (obligatorias) y
``S3_ENDPOINT_URL`` (solo para probar contra MinIO; vacía en AWS).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date
from typing import Any, Callable
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VALID = "VALID"
INVALID = "INVALID"
REPORTS_PREFIX = "reports/"
METADATA_PREFIX = "metadata/"
HTTP_TIMEOUT_SECONDS = 10

DAILY_SUMMARY_KEY = re.compile(r"^reports/daily/(\d{4}-\d{2}-\d{2})/summary\.json$")
DAILY_SUMMARY_FIELDS = (
    "report_date",
    "status",
    "missing_warehouses",
    "warehouses",
    "movements_by_type_and_warehouse",
    "net_change_by_sku",
    "top_5_skus",
)
DAILY_SUMMARY_STATUSES = ("SUCCEEDED", "PARTIAL")


def log(event: str, correlation_id: str | None, **fields: Any) -> None:
    """Una línea JSON por evento, con el correlation_id para buscar en CloudWatch."""

    logger.info(json.dumps({"event": event, "correlation_id": correlation_id, **fields}, default=str))


def validate_report(key: str, raw: bytes) -> tuple[str, str | None, int | None]:
    """Devuelve ``(estado, motivo, registros)``.

    - ``reports/daily/<fecha>/summary.json``: debe traer los campos del resumen del
      batch (J-08), un ``status`` conocido y la misma ``report_date`` que la llave.
      Sus registros son los movimientos leídos de las bodegas.
    - Otro objeto bajo ``reports/``: solo se exige que sea un objeto JSON; el
      número de registros se deja sin calcular (``None``) porque su formato no está definido.
    """

    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        return INVALID, f"No es JSON válido: {exc}", None
    if not isinstance(report, dict):
        return INVALID, "El reporte debe ser un objeto JSON", None

    match = DAILY_SUMMARY_KEY.match(key)
    if match is None:
        return VALID, None, None

    missing = [field for field in DAILY_SUMMARY_FIELDS if field not in report]
    if missing:
        return INVALID, f"Faltan campos obligatorios: {', '.join(missing)}", None
    if report["status"] not in DAILY_SUMMARY_STATUSES:
        return INVALID, f"status desconocido: {report['status']!r}", None
    try:
        date.fromisoformat(report["report_date"])
    except (TypeError, ValueError):
        return INVALID, "report_date no es una fecha YYYY-MM-DD", None
    if report["report_date"] != match.group(1):
        return INVALID, "report_date no coincide con la fecha de la llave", None
    if not isinstance(report["warehouses"], dict):
        return INVALID, "warehouses debe ser un objeto", None

    records = 0
    for warehouse in report["warehouses"].values():
        movements = warehouse.get("movements") if isinstance(warehouse, dict) else None
        if movements is not None:
            if isinstance(movements, bool) or not isinstance(movements, int) or movements < 0:
                return INVALID, "movements debe ser un entero no negativo", None
            records += movements
    return VALID, None, records


def post_report(url: str, api_key: str, correlation_id: str | None, body: dict) -> None:
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS):
            return
    except urllib.error.HTTPError as exc:
        # La misma llave se vuelve a subir cuando se repite el batch de un día; si la
        # central ya la tiene registrada responde 409 y no hay nada que reintentar.
        if exc.code == 409:
            return
        raise


def process_object(
    s3: Any,
    bucket: str,
    key: str,
    *,
    central_url: str,
    api_key: str,
    post: Callable[..., None] | None = None,
) -> dict[str, Any]:
    post = post or post_report
    response = s3.get_object(Bucket=bucket, Key=key)
    raw = response["Body"].read()
    correlation_id = (response.get("Metadata") or {}).get("correlation-id")

    status, reason, records = validate_report(key, raw)
    metadata_key = METADATA_PREFIX + key
    result = {
        "object_key": key,
        "status": status,
        "size": len(raw),
        "checksum": hashlib.sha256(raw).hexdigest(),
        "record_count": records,
        "reason": reason,
        "correlation_id": correlation_id,
    }

    s3.put_object(
        Bucket=bucket,
        Key=metadata_key,
        Body=json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
        Metadata={"correlation-id": correlation_id} if correlation_id else {},
    )
    post(
        f"{central_url}/internal/reports",
        api_key,
        correlation_id,
        {
            "object_key": key,
            "status": status,
            "size": result["size"],
            "checksum": result["checksum"],
            "metadata": {
                "record_count": records,
                "reason": reason,
                "correlation_id": correlation_id,
                "metadata_key": metadata_key,
            },
        },
    )

    log(
        "report_validated" if status == VALID else "report_invalid",
        correlation_id,
        bucket=bucket,
        object_key=key,
        status=status,
        reason=reason,
        size=result["size"],
        sha256=result["checksum"],
        record_count=records,
        metadata_key=metadata_key,
    )
    return result


def lambda_handler(event: dict, context: Any) -> dict[str, int]:
    central_url = os.environ.get("CENTRAL_API_URL", "").rstrip("/")
    api_key = os.environ.get("CENTRAL_API_KEY", "")
    if not central_url or not api_key:
        raise RuntimeError("CENTRAL_API_URL y CENTRAL_API_KEY son obligatorias")

    s3 = None  # el cliente se crea al llegar el primer reporte
    counts = {VALID: 0, INVALID: 0, "ignored": 0}

    for record in event.get("Records", []):
        if record.get("eventSource") != "aws:s3":
            counts["ignored"] += 1
            continue
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        # Nunca procesar lo que la propia Lambda escribe ni nada fuera de reports/*.json.
        if not key.startswith(REPORTS_PREFIX) or not key.endswith(".json"):
            counts["ignored"] += 1
            continue
        if s3 is None:
            s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None)
        result = process_object(s3, bucket, key, central_url=central_url, api_key=api_key)
        counts[result["status"]] += 1

    log("lambda_finished", None, **counts)
    return {"processed": counts[VALID], "invalid": counts[INVALID], "ignored": counts["ignored"]}
