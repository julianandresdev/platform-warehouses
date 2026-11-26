"""Prueba de integración del ciclo RabbitMQ; requiere un broker accesible."""

from __future__ import annotations

import os
import threading
import time
import unittest
import uuid

from common.correlation import get_correlation_id
from common.rabbit import (
    connect,
    consume,
    dead_letter_queue_name,
    declare_topology,
    publish,
    retry_queue_name,
)


RABBITMQ_URL = os.getenv("RABBITMQ_URL")


@unittest.skipUnless(RABBITMQ_URL, "define RABBITMQ_URL para usar RabbitMQ")
class RabbitIntegrationTest(unittest.TestCase):
    def test_publish_consume_and_correlation_context(self) -> None:
        queue = f"integration.{uuid.uuid4()}"
        correlation_id = "COR-INTEGRATION-TEST"
        received: list[tuple[dict, str | None]] = []
        handled = threading.Event()
        stop = threading.Event()

        setup_connection = connect(RABBITMQ_URL)
        setup_channel = setup_connection.channel()
        declare_topology(setup_channel)
        setup_channel.queue_declare(queue=queue, durable=False, auto_delete=False)
        setup_channel.queue_bind(
            queue=queue,
            exchange="central.events",
            routing_key="central.report.registered",
        )
        setup_connection.close()

        def handler(message: dict) -> None:
            received.append((message, get_correlation_id()))
            handled.set()

        consumer_thread = threading.Thread(
            target=consume,
            kwargs={"queue": queue, "handler": handler, "url": RABBITMQ_URL, "stop_event": stop},
            daemon=True,
        )
        consumer_thread.start()
        producer = None

        try:
            # Wait until basic_consume is registered before publishing.
            deadline = time.monotonic() + 10
            producer = connect(RABBITMQ_URL)
            producer_channel = producer.channel()
            while time.monotonic() < deadline:
                result = producer_channel.queue_declare(queue=queue, passive=True)
                if result.method.consumer_count:
                    break
                time.sleep(0.1)
            else:
                self.fail("el consumidor no se registró en RabbitMQ")

            envelope = {
                "event_id": str(uuid.uuid4()),
                "event_type": "REPORT_REGISTERED",
                "event_version": 1,
                "occurred_at": "2026-11-22T12:00:00Z",
                "correlation_id": correlation_id,
                "source": "central",
                "payload": {"key": "reports/test.json", "size": 1, "checksum": "abc"},
            }
            publish(
                envelope,
                "central.events",
                "central.report.registered",
                channel=producer_channel,
            )
            self.assertTrue(handled.wait(timeout=10), "mensaje no recibido a tiempo")
            self.assertEqual(received, [(envelope, correlation_id)])
        finally:
            if producer is not None and producer.is_open:
                producer.close()
            stop.set()
            consumer_thread.join(timeout=5)
            cleanup = connect(RABBITMQ_URL)
            cleanup_channel = cleanup.channel()
            for name in (queue, retry_queue_name(queue), dead_letter_queue_name(queue)):
                cleanup_channel.queue_delete(queue=name, if_unused=False, if_empty=False)
            cleanup.close()
            self.assertFalse(consumer_thread.is_alive(), "el consumidor no terminó")


if __name__ == "__main__":
    unittest.main()
