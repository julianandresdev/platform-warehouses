"""Integration coverage for asynchronous warehouse reports and cache invalidation."""

from __future__ import annotations

import os
import threading
import time
import uuid

import pytest


@pytest.fixture(scope="module")
def resources():
    if not os.getenv("DATABASE_URL") or not os.getenv("REDIS_URL"):
        pytest.skip("DATABASE_URL y REDIS_URL son necesarios para D-04")

    import cache
    import config
    from app import app
    from common.events import new_event
    from common.rabbit import connect, consume, declare_topology, publish
    from database import SessionLocal, get_db
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from workers.cache_invalidation import handle_invalidation
    from workers.reports import process_report_event

    cache._client = None
    config.CACHE_ENABLED = True
    config.CACHE_INVALIDATION = "async"

    def override_db():
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        yield {
            "app": app,
            "cache": cache,
            "config": config,
            "new_event": new_event,
            "connect": connect,
            "consume": consume,
            "declare_topology": declare_topology,
            "publish": publish,
            "SessionLocal": SessionLocal,
            "text": text,
            "TestClient": TestClient,
            "handle_invalidation": handle_invalidation,
            "process_report_event": process_report_event,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        cache._client = None


def test_async_cache_invalidation_deletes_redis_key(resources):
    cache = resources["cache"]
    config = resources["config"]
    sku = f"D04-{uuid.uuid4().hex[:12]}"
    key = cache.inventory_key(sku)
    cache._redis().set(key, '{"quantity": 7}')
    event = resources["new_event"](
        "INVENTORY_UPDATED",
        {"warehouse_id": config.WAREHOUSE_ID, "sku": sku, "quantity": 7},
        source=f"warehouse-{config.WAREHOUSE_ID}",
        correlation_id="D04-CACHE-TEST",
    )

    resources["handle_invalidation"](event.model_dump(mode="json"))

    assert cache._redis().get(key) is None


def test_cache_queue_replays_backlog_after_consumer_starts(resources):
    rabbit_url = os.getenv("RABBITMQ_URL")
    if not rabbit_url:
        pytest.skip("RABBITMQ_URL es necesario para D-04")

    cache = resources["cache"]
    warehouse_id = resources["config"].WAREHOUSE_ID
    sku = f"D04-QUEUE-{uuid.uuid4().hex[:10]}"
    key = cache.inventory_key(sku)
    cache._redis().set(key, '{"quantity": 11}')
    event = resources["new_event"](
        "INVENTORY_UPDATED",
        {"warehouse_id": warehouse_id, "sku": sku, "quantity": 11},
        source=f"warehouse-{warehouse_id}",
        correlation_id="D04-QUEUE-REPLAY",
    )
    queue = f"{warehouse_id.lower()}.cache-invalidation"
    connection = resources["connect"](rabbit_url)
    channel = connection.channel()
    resources["declare_topology"](channel, warehouse_ids=(warehouse_id,))
    stop_event = threading.Event()
    errors = []

    try:
        queued_before = channel.queue_declare(
            queue=queue, passive=True
        ).method.message_count
        resources["publish"](
            event,
            exchange="warehouse.events",
            routing_key=f"warehouse.{warehouse_id}.inventory.updated",
            channel=channel,
        )
        queued_after = channel.queue_declare(
            queue=queue, passive=True
        ).method.message_count
        assert queued_after > queued_before, "el mensaje debe quedar en cola sin consumidor"
        thread = threading.Thread(
            target=lambda: _consume_cache_queue(resources, queue, rabbit_url, stop_event, errors),
            daemon=True,
        )
        thread.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and cache._redis().exists(key):
            time.sleep(0.1)
        stop_event.set()
        thread.join(timeout=5)
        assert not thread.is_alive(), "el consumidor no se detuvo"
        assert not errors, errors
        assert cache._redis().exists(key) == 0
    finally:
        stop_event.set()
        if channel.is_open:
            channel.close()
        if connection.is_open:
            connection.close()
        cache._redis().delete(key)


def _consume_cache_queue(resources, queue, rabbit_url, stop_event, errors):
    try:
        resources["consume"](
            queue,
            resources["handle_invalidation"],
            url=rabbit_url,
            stop_event=stop_event,
        )
    except Exception as error:
        errors.append(error)


def test_report_api_outbox_and_worker_complete_job(resources):
    SessionLocal = resources["SessionLocal"]
    text = resources["text"]
    app = resources["app"]
    test_client = resources["TestClient"]
    sku = f"D04-{uuid.uuid4().hex[:12]}"
    correlation_id = f"D04-REPORT-{uuid.uuid4().hex[:8]}"
    product_id = None
    job_id = None
    event_id = None

    with SessionLocal.begin() as session:
        product_id = session.execute(
            text(
                "INSERT INTO products (sku, name, unit) "
                "VALUES (:sku, :sku, 'unit') RETURNING id"
            ),
            {"sku": sku},
        ).scalar_one()
        session.execute(
            text(
                """
                INSERT INTO inventory_movements (
                    product_id, warehouse_id, type, quantity, created_at
                )
                VALUES
                    (:product_id, :warehouse_id, 'RECEIPT', 4, '2099-06-01 12:00:00'),
                    (:product_id, :warehouse_id, 'SHIPMENT', 2, '2099-06-01 12:00:00'),
                    (:product_id, :warehouse_id, 'ADJUSTMENT', -1, '2099-06-01 12:00:00')
                """
            ),
            {"product_id": product_id, "warehouse_id": resources["config"].WAREHOUSE_ID},
        )

    try:
        with test_client(app) as client:
            response = client.post(
                "/reports",
                headers={
                    "X-API-Key": os.getenv("API_KEY", "e02-test-key"),
                    "X-Correlation-ID": correlation_id,
                },
                json={
                    "start_at": "2099-01-01T00:00:00Z",
                    "end_at": "2100-01-01T00:00:00Z",
                },
            )
            assert response.status_code == 202, response.text
            assert response.headers["X-Correlation-ID"] == correlation_id
            job_id = response.json()["job_id"]
            assert response.json()["status"] == "PROCESSING"

        with SessionLocal() as session:
            row = session.execute(
                text(
                    """
                    SELECT o.event_id, o.payload, o.published_at, j.status
                    FROM outbox AS o
                    JOIN report_jobs AS j
                      ON j.job_id = (o.payload->'payload'->>'job_id')::uuid
                    WHERE j.job_id = CAST(:job_id AS UUID)
                    """
                ),
                {"job_id": job_id},
            ).mappings().one()
        event_id = row["event_id"]
        assert row["published_at"] is None
        assert row["status"] == "PROCESSING"
        assert row["payload"]["correlation_id"] == correlation_id

        resources["process_report_event"](row["payload"])
        resources["process_report_event"](row["payload"])

        with test_client(app) as client:
            response = client.get(
                f"/reports/jobs/{job_id}",
                headers={"X-API-Key": os.getenv("API_KEY", "e02-test-key")},
            )
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["status"] == "DONE"
        assert report["result"]["warehouse_id"] == resources["config"].WAREHOUSE_ID
        matching_sku = next(
            item for item in report["result"]["top_skus"] if item["sku"] == sku
        )
        assert matching_sku["units_moved"] == 7
    finally:
        with SessionLocal.begin() as session:
            if event_id is not None:
                session.execute(
                    text("DELETE FROM outbox WHERE event_id = :event_id"),
                    {"event_id": event_id},
                )
            if job_id is not None:
                session.execute(
                    text("DELETE FROM report_jobs WHERE job_id = CAST(:job_id AS UUID)"),
                    {"job_id": job_id},
                )
            if product_id is not None:
                session.execute(
                    text("DELETE FROM inventory_movements WHERE product_id = :product_id"),
                    {"product_id": product_id},
                )
                session.execute(
                    text("DELETE FROM products WHERE id = :product_id"),
                    {"product_id": product_id},
                )
