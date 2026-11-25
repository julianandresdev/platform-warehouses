"""Cliente S3 compartido: MinIO en local, S3 en AWS (S-05, ADR-0011).

Se configura solo por entorno, así el mismo código corre en los dos sitios:

- ``S3_ENDPOINT_URL``: URL de MinIO. Vacío o sin definir en AWS.
- ``S3_BUCKET``: nombre del bucket (por defecto ``warehouse-platform``).
- ``AWS_DEFAULT_REGION``, ``AWS_ACCESS_KEY_ID`` y ``AWS_SECRET_ACCESS_KEY``:
  los lee boto3 como siempre.

Estructura del bucket (ver docs/fases/fase-8.md): ``warehouses/``, ``reports/``,
``metadata/``, ``audit/`` y ``exports/``.
"""

from __future__ import annotations

import builtins
import json
import os
from typing import Any

import boto3

DEFAULT_BUCKET = "warehouse-platform"
DEFAULT_REGION = "us-east-1"


def bucket_name() -> str:
    return os.getenv("S3_BUCKET") or DEFAULT_BUCKET


def get_client() -> Any:
    """Cliente boto3 de S3; usa ``S3_ENDPOINT_URL`` solo si está definida."""

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        region_name=os.getenv("AWS_DEFAULT_REGION") or DEFAULT_REGION,
    )


def put_json(
    key: str,
    obj: Any,
    metadata: dict[str, str] | None = None,
    *,
    client: Any = None,
    bucket: str | None = None,
) -> None:
    """Guarda ``obj`` como JSON UTF-8 en ``key`` con los metadatos indicados.

    Los metadatos son pares texto-texto (p. ej. ``{"correlation-id": "COR-..."}``).
    Escribir dos veces la misma llave reemplaza el objeto.
    """

    body = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    (client or get_client()).put_object(
        Bucket=bucket or bucket_name(),
        Key=key,
        Body=body,
        ContentType="application/json",
        Metadata={str(k): str(v) for k, v in (metadata or {}).items()},
    )


def list(  # noqa: A001 - el nombre lo fija el issue #26
    prefix: str = "",
    *,
    client: Any = None,
    bucket: str | None = None,
) -> builtins.list[str]:
    """Llaves del bucket que empiezan por ``prefix`` (recorre todas las páginas)."""

    paginator = (client or get_client()).get_paginator("list_objects_v2")
    keys: builtins.list[str] = []
    for page in paginator.paginate(Bucket=bucket or bucket_name(), Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys
