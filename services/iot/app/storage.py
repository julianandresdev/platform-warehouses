"""Idempotent storage worker for IoT readings."""

from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge, Histogram, start_http_server
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from common.events import EventEnvelope
from common.logging import configure_logging
from common.rabbit import PermanentError, connect, consume, declare_topology
from app import config
from app.schemas import SensorReading

logger = logging.getLogger("iot-storage-worker")
stop_event = threading.Event()
deliveries = Counter("iot_storage_deliveries_total", "IoT queue deliveries, including redeliveries")
stored_unique = Gauge("iot_readings_stored_unique_total", "Unique IoT readings persisted")
duplicates_discarded = Gauge("iot_duplicates_discarded_total", "Duplicate IoT readings discarded")
out_of_order_total = Gauge("iot_readings_out_of_order_total", "Unique readings received out of sequence")
sequence_gaps = Gauge("iot_sequence_gaps", "Missing sequence numbers below each sensor high-water mark")
processing_latency = Histogram(
    "iot_storage_latency_seconds",
    "Time from sensor timestamp to database processing",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _snapshot_metrics() -> None:
    with engine.connect() as connection:
        stats = connection.execute(
            text("""SELECT received, stored_unique, duplicates_discarded, out_of_order
                   FROM sensor_ingestion_stats WHERE singleton = TRUE""")
        ).mappings().one()
        gaps = connection.execute(
            text("""SELECT COALESCE(SUM(GREATEST(s.last_sequence - COALESCE(r.reading_count, 0), 0)), 0)
                   FROM sensor_state AS s
                   LEFT JOIN (
                       SELECT sensor_id, COUNT(*) AS reading_count
                       FROM sensor_readings GROUP BY sensor_id
                   ) AS r USING (sensor_id)""")
        ).scalar_one()
    stored_unique.set(stats["stored_unique"])
    duplicates_discarded.set(stats["duplicates_discarded"])
    out_of_order_total.set(stats["out_of_order"])
    sequence_gaps.set(gaps)


def process_reading(message: dict) -> None:
    try:
        event = EventEnvelope.model_validate(message)
    except ValidationError as exc:
        raise PermanentError(f"Sobre IoT inválido: {exc}") from exc
    if event.event_type == "SENSOR_ALERT":
        # Alerts use the same exchange but are output events, not source readings.
        return
    if event.event_type != "SENSOR_READING" or event.event_version != 1:
        raise PermanentError("Tipo o versión de evento IoT no soportado")
    try:
        reading = SensorReading.model_validate(event.payload)
    except ValidationError as exc:
        raise PermanentError(f"Lectura IoT inválida: {exc}") from exc
    if reading.event_id != event.event_id:
        raise PermanentError("event_id del sobre no coincide con la lectura")

    deliveries.inc()
    now = datetime.now(timezone.utc)
    age = max(0.0, (now - reading.timestamp).total_seconds())
    processing_latency.observe(age)

    with SessionLocal.begin() as session:
        state = session.execute(
            text("SELECT last_sequence FROM sensor_state WHERE sensor_id=:sensor_id FOR UPDATE"),
            {"sensor_id": reading.sensor_id},
        ).mappings().first()
        is_out_of_order = state is not None and reading.sequence_number <= state["last_sequence"]
        inserted = session.execute(
            text("""INSERT INTO sensor_readings (
                       event_id, warehouse_id, sensor_id, sensor_type, value,
                       sequence_number, observed_at, ingested_at, out_of_order
                   ) VALUES (
                       :event_id, :warehouse_id, :sensor_id, :sensor_type, :value,
                       :sequence_number, :observed_at, :ingested_at, :out_of_order
                   ) ON CONFLICT (event_id) DO NOTHING RETURNING event_id"""),
            {
                "event_id": reading.event_id,
                "warehouse_id": reading.warehouse_id,
                "sensor_id": reading.sensor_id,
                "sensor_type": reading.sensor_type.value,
                "value": reading.value,
                "sequence_number": reading.sequence_number,
                "observed_at": reading.timestamp,
                "ingested_at": now,
                "out_of_order": is_out_of_order,
            },
        ).scalar_one_or_none()

        if inserted is None:
            session.execute(
                text("""UPDATE sensor_ingestion_stats
                       SET received=received+1, duplicates_discarded=duplicates_discarded+1
                       WHERE singleton=TRUE""")
            )
            logger.info("iot_duplicate_discarded", extra={"event_id": str(reading.event_id)})
        else:
            session.execute(
                text("UPDATE sensor_ingestion_stats SET received=received+1, stored_unique=stored_unique+1 WHERE singleton=TRUE")
            )
            if is_out_of_order:
                session.execute(
                    text("UPDATE sensor_ingestion_stats SET out_of_order=out_of_order+1 WHERE singleton=TRUE")
                )
                logger.info(
                    "iot_reading_out_of_order",
                    extra={"sensor_id": reading.sensor_id, "sequence_number": reading.sequence_number},
                )
            elif state is None:
                session.execute(
                    text("""INSERT INTO sensor_state (
                               sensor_id, warehouse_id, sensor_type, last_sequence,
                               last_value, last_ts
                           ) VALUES (:sensor_id, :warehouse_id, :sensor_type,
                                     :sequence_number, :value, :timestamp)"""),
                    {
                        "sensor_id": reading.sensor_id,
                        "warehouse_id": reading.warehouse_id,
                        "sensor_type": reading.sensor_type.value,
                        "sequence_number": reading.sequence_number,
                        "value": reading.value,
                        "timestamp": reading.timestamp,
                    },
                )
            else:
                session.execute(
                    text("""UPDATE sensor_state SET last_sequence=:sequence_number,
                               last_value=:value, last_ts=:timestamp, updated_at=now()
                           WHERE sensor_id=:sensor_id"""),
                    {
                        "sensor_id": reading.sensor_id,
                        "sequence_number": reading.sequence_number,
                        "value": reading.value,
                        "timestamp": reading.timestamp,
                    },
                )
    _snapshot_metrics()


def _shutdown(signum, frame) -> None:
    logger.info("iot_storage_shutdown_requested", extra={"signal": signum})
    stop_event.set()


def run() -> None:
    configure_logging("iot-storage-worker", None, config.LOG_LEVEL)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    _snapshot_metrics()
    start_http_server(9104, addr="0.0.0.0")
    failures = 0
    while not stop_event.is_set():
        connection = None
        try:
            connection = connect(config.RABBITMQ_URL, attempts=3)
            declare_topology(connection.channel())
            logger.info("iot_storage_ready", extra={"queue": "iot.storage"})
            consume("iot.storage", process_reading, connection=connection, stop_event=stop_event)
            failures = 0
        except Exception:
            if not stop_event.is_set():
                logger.exception("iot_storage_worker_failed")
                failures += 1
                stop_event.wait(min(0.5 * (2 ** min(failures, 6)), 30))
        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    run()

