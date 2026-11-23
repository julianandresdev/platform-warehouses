"""End-to-end test for a persisted outbox event reaching RabbitMQ."""

from __future__ import annotations

import json
import os
import unittest
import uuid


DATABASE_URL = os.getenv("DATABASE_URL")
RABBITMQ_URL = os.getenv("RABBITMQ_URL")


@unittest.skipUnless(
    DATABASE_URL and RABBITMQ_URL,
    "define DATABASE_URL and RABBITMQ_URL to test the outbox relay",
)
class OutboxRelayIntegrationTest(unittest.TestCase):
    def test_confirmed_event_is_marked_published_and_routed(self) -> None:
        from sqlalchemy import text

        from common.events import new_event
        from common.outbox import add_event
        from common.rabbit import connect, declare_topology
        from config import WAREHOUSE_ID
        from database import SessionLocal
        from workers.outbox_relay import relay_pending_batch

        event = new_event(
            "INVENTORY_UPDATED",
            {
                "warehouse_id": WAREHOUSE_ID,
                "sku": f"OUTBOX-{uuid.uuid4()}",
                "quantity": 8,
                "reserved_quantity": 0,
                "version": 1,
                "movement_type": "RECEIPT",
            },
            source=f"warehouse-{WAREHOUSE_ID}",
        )
        event_id = str(event.event_id)
        routing_key = f"warehouse.{WAREHOUSE_ID}.inventory.updated"
        queue = f"integration.outbox.{uuid.uuid4()}"
        connection = connect(RABBITMQ_URL)
        channel = connection.channel()

        try:
            declare_topology(channel, warehouse_ids=(WAREHOUSE_ID,))
            channel.queue_declare(queue=queue, durable=False, auto_delete=False)
            channel.queue_bind(
                queue=queue,
                exchange="warehouse.events",
                routing_key=routing_key,
            )

            with SessionLocal() as session, session.begin():
                add_event(
                    session,
                    event,
                    exchange="warehouse.events",
                    routing_key=routing_key,
                )

            published, failed = relay_pending_batch(
                SessionLocal, channel, batch_size=1000
            )
            self.assertGreaterEqual(published, 1)
            self.assertFalse(failed)

            with SessionLocal() as session:
                row = session.execute(
                    text(
                        """
                        SELECT published_at, attempts
                        FROM outbox
                        WHERE event_id = CAST(:event_id AS UUID)
                        """
                    ),
                    {"event_id": event_id},
                ).one()
            self.assertIsNotNone(row.published_at)
            self.assertEqual(row.attempts, 1)

            method, properties, body = channel.basic_get(queue, auto_ack=True)
            self.assertIsNotNone(method)
            self.assertEqual(properties.message_id, event_id)
            self.assertEqual(json.loads(body), event.model_dump(mode="json"))
        finally:
            with SessionLocal() as session, session.begin():
                session.execute(
                    text("DELETE FROM outbox WHERE event_id = CAST(:event_id AS UUID)"),
                    {"event_id": event_id},
                )
            if channel.is_open:
                channel.queue_delete(queue=queue)
            if connection.is_open:
                connection.close()


if __name__ == "__main__":
    unittest.main()
