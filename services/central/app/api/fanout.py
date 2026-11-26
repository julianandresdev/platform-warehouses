import asyncio
import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app import config


async def query_fanout(sku, client):
    urls = dict(
        item.strip().split("=", 1)
        for item in config.WAREHOUSE_URLS.split(",")
        if item.strip()
    )

    if not urls:
        raise HTTPException(503, "WAREHOUSE_URLS no configurada")

    api_key = os.getenv("WAREHOUSE_API_KEY", "dev-api-key")

    async def query_warehouse(warehouse_id, url):
        try:
            response = await asyncio.wait_for(
                client.get(
                    f"{url.rstrip('/')}/inventory/{quote(sku, safe='')}",
                    headers={"X-API-Key": api_key},
                ),
                timeout=0.5,
            )

            if response.status_code == 404:
                return warehouse_id, "not_found", None

            response.raise_for_status()
            data = response.json()

            if data["warehouse_id"] != warehouse_id:
                raise ValueError("Identidad de bodega incorrecta")

            return warehouse_id, "ok", {
                "warehouse_id": warehouse_id,
                "quantity": data["quantity"],
                "reserved_quantity": data["reserved_quantity"],
                "available_quantity": data["available_quantity"],
                "version": data["version"],
                "updated_at": data["updated_at"],
                "stale": False,
            }

        except (
            httpx.HTTPError,
            asyncio.TimeoutError,
            ValueError,
            KeyError,
            TypeError,
        ):
            return warehouse_id, "unavailable", None

    results = await asyncio.gather(
        *(query_warehouse(w, url) for w, url in urls.items())
    )

    warehouses = [
        data for _, state, data in results if state == "ok"
    ]

    unavailable = [
        w for w, state, _ in results if state == "unavailable"
    ]

    not_found = [
        w for w, state, _ in results if state == "not_found"
    ]

    if not warehouses:
        if unavailable:
            raise HTTPException(
                503,
                detail={"unavailable": unavailable},
            )
        raise HTTPException(404, "Inventario no encontrado")

    quantity = sum(w["quantity"] for w in warehouses)
    reserved = sum(w["reserved_quantity"] for w in warehouses)

    return {
        "sku": sku,
        "mode": "fanout",
        "total_quantity": quantity,
        "total_reserved": reserved,
        "total_available": quantity - reserved,
        "as_of": datetime.now(timezone.utc),
        "partial": bool(unavailable),
        "unavailable": unavailable,
        "not_found": not_found,
        "warehouses": warehouses,
    }
