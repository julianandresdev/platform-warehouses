"""Temperature alert worker with sequence-aware streaks and a DB outbox."""

from __future__ import annotations

import logging
import signal
import threading
from uuid import uuid4

from prometheus_client import Counter, Gauge, start_http_server
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from common.events import EventEnvelope
from common.logging import configure_logging
from common.rabbit import PermanentError, connect, consume, declare_topology, publish
from app import config
from app.schemas import SensorReading

logger = logging.getLogger("iot-alert-worker")
stop_event = threading.Event()
alerts_created = Counter("iot_temperature_alerts_created_total", "Temperature alerts created")
active_sensors = Gauge("iot_temperature_alerts_active_sensors", "Sensors with an active temperature alert")

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def advance_streak(
    sequence_number: int,
    value: float,
    last_sequence: int,
    streak: int,
    is_active: bool,
    threshold: float,
) -> tuple[int, int, bool, bool]:
    """Return updated sequence, streak, active state and new-alert decision."""
    if sequence_number <= last_sequence:
        return last_sequence, streak, is_active, False
    if sequence_number != last_sequence + 1:
        streak = 0
    if value > threshold:
        streak += 1
        create_alert = streak >= 3 and not is_active
        return sequence_number, streak, is_active or create_alert, create_alert
    return sequence_number, 0, False, False


def _refresh_active_metric() -> None:
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM sensor_alert_state WHERE is_active=TRUE")
        ).scalar_one()
    active_sensors.set(count)


def process_temperature_reading(message: dict) -> None:
    try:
        event = EventEnvelope.model_validate(message)
    except ValidationError as exc:
        raise PermanentError(f"Sobre IoT inválido: {exc}") from exc
    if event.event_type != "SENSOR_READING" or event.event_version != 1:
        raise PermanentError("Evento no soportado por el worker de alertas")
    try:
        reading = SensorReading.model_validate(event.payload)
    except ValidationError as exc:
        raise PermanentError(f"Lectura IoT inválida: {exc}") from exc
    if reading.sensor_type.value != "temperature":
        return
    if event.event_id != reading.event_id:
        raise PermanentError("event_id del sobre no coincide con la lectura")

    with SessionLocal.begin() as session:
        inserted = session.execute(
            text("""INSERT INTO sensor_processed_messages(event_id, consumer)
                   VALUES (:event_id, 'iot.alerts') ON CONFLICT DO NOTHING
                   RETURNING event_id"""),
            {"event_id": reading.event_id},
        ).scalar_one_or_none()
        if inserted is None:
            return

        state = session.execute(
            text("""SELECT last_sequence, above_threshold_streak, is_active
                   FROM sensor_alert_state WHERE sensor_id=:sensor_id FOR UPDATE"""),
            {"sensor_id": reading.sensor_id},
        ).mappings().first()
        if state is not None and reading.sequence_number <= state["last_sequence"]:
            return

        last_sequence = state["last_sequence"] if state else 0
        streak = state["above_threshold_streak"] if state else 0
        is_active = state["is_active"] if state else False
        next_sequence, streak, is_active, create_alert = advance_streak(
            reading.sequence_number,
            reading.value,
            last_sequence,
            streak,
            is_active,
            config.TEMPERATURE_THRESHOLD,
        )
        if next_sequence == last_sequence:
            return

        new_alert_id = None
        if create_alert:
            new_alert_id = uuid4()
            is_active = True
            session.execute(
                text("""INSERT INTO sensor_alerts(
                           alert_id, sensor_id, warehouse_id, sequence_number,
                           value, threshold, observed_at
                       ) VALUES (
                           :alert_id, :sensor_id, :warehouse_id, :sequence_number,
                           :value, :threshold, :observed_at
                       )"""),
                {
                    "alert_id": new_alert_id,
                    "sensor_id": reading.sensor_id,
                    "warehouse_id": reading.warehouse_id,
                    "sequence_number": next_sequence,
                    "value": reading.value,
                    "threshold": config.TEMPERATURE_THRESHOLD,
                    "observed_at": reading.timestamp,
                },
            )

        if state is None:
            session.execute(
                text("""INSERT INTO sensor_alert_state(
                           sensor_id, warehouse_id, last_sequence,
                           above_threshold_streak, is_active
                       ) VALUES (:sensor_id, :warehouse_id, :sequence_number, :streak, :active)"""),
                {
                    "sensor_id": reading.sensor_id,
                    "warehouse_id": reading.warehouse_id,
                    "sequence_number": next_sequence,
                    "streak": streak,
                    "active": is_active,
                },
            )
        else:
            session.execute(
                text("""UPDATE sensor_alert_state
                       SET last_sequence=:sequence_number,
                           above_threshold_streak=:streak, is_active=:active,
                           updated_at=now()
                       WHERE sensor_id=:sensor_id"""),
                {
                    "sensor_id": reading.sensor_id,
                    "sequence_number": next_sequence,
                    "streak": streak,
                    "active": is_active,
                },
            )

    if new_alert_id is not None:
        alerts_created.inc()
        logger.warning(
            "iot_temperature_alert_created",
            extra={"sensor_id": reading.sensor_id, "alert_id": str(new_alert_id)},
        )
    _refresh_active_metric()


def _publish_alert_outbox() -> None:
    with SessionLocal() as session:
        rows = session.execute(
            text("""SELECT alert_id, sensor_id, warehouse_id, sequence_number,
                          value, threshold, observed_at
                   FROM sensor_alerts WHERE published_at IS NULL
                   ORDER BY created_at LIMIT 100""")
        ).mappings().all()
    for row in rows:
        envelope = EventEnvelope(
            event_id=row["alert_id"],
            event_type="SENSOR_ALERT",
            event_version=1,
            occurred_at=row["observed_at"],
            correlation_id=str(row["alert_id"]),
            source="iot-alert-worker",
            payload={
                "warehouse_id": row["warehouse_id"],
                "sensor_id": row["sensor_id"],
                "sensor_type": "temperature",
                "value": row["value"],
                "threshold": row["threshold"],
                "sequence_number": row["sequence_number"],
                "timestamp": row["observed_at"].isoformat(),
            },
        )
        publish(envelope, "iot.readings", f"iot.{row['warehouse_id']}.temperature.alert")
        with SessionLocal.begin() as session:
            session.execute(
                text("UPDATE sensor_alerts SET published_at=now() WHERE alert_id=:alert_id"),
                {"alert_id": row["alert_id"]},
            )


def _outbox_loop() -> None:
    while not stop_event.is_set():
        try:
            _publish_alert_outbox()
        except Exception:
            logger.exception("iot_alert_outbox_failed")
        stop_event.wait(0.5)


def _shutdown(signum, frame) -> None:
    logger.info("iot_alert_shutdown_requested", extra={"signal": signum})
    stop_event.set()


def run() -> None:
    configure_logging("iot-alert-worker", None, config.LOG_LEVEL)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    _refresh_active_metric()
    start_http_server(9105, addr="0.0.0.0")
    relay = threading.Thread(target=_outbox_loop, name="iot-alert-outbox", daemon=True)
    relay.start()
    failures = 0
    while not stop_event.is_set():
        connection = None
        try:
            connection = connect(config.RABBITMQ_URL, attempts=3)
            declare_topology(connection.channel())
            logger.info("iot_alert_worker_ready", extra={"queue": "iot.alerts"})
            consume(
                "iot.alerts", process_temperature_reading,
                connection=connection, stop_event=stop_event,
            )
            failures = 0
        except Exception:
            if not stop_event.is_set():
                logger.exception("iot_alert_worker_failed")
                failures += 1
                stop_event.wait(min(0.5 * (2 ** min(failures, 6)), 30))
        finally:
            if connection is not None and connection.is_open:
                connection.close()
    relay.join(timeout=5)


if __name__ == "__main__":
    run()

