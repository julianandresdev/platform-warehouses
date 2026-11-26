"""Durable SQLite store-and-forward queue for simulated sensors."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SensorSpool:
    def __init__(self, path: str) -> None:
        spool_path = Path(path)
        spool_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(spool_path, timeout=30)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sensor_sequences (
                sensor_id TEXT PRIMARY KEY,
                sequence_number INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                sensor_id TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_pending_sensor_sequence
                ON pending_readings (sensor_id, sequence_number);
            """
        )
        self.connection.commit()

    def add(self, sensor_id: str, payload: dict[str, Any]) -> int:
        event_id = str(payload["event_id"])
        sequence = int(payload["sequence_number"])
        with self.connection:
            self.connection.execute(
                """INSERT INTO sensor_sequences(sensor_id, sequence_number)
                   VALUES (?, ?) ON CONFLICT(sensor_id) DO UPDATE
                   SET sequence_number = excluded.sequence_number""",
                (sensor_id, sequence),
            )
            result = self.connection.execute(
                """INSERT INTO pending_readings(
                       event_id, sensor_id, sequence_number, payload
                   ) VALUES (?, ?, ?, ?)""",
                (event_id, sensor_id, sequence, json.dumps(payload, separators=(",", ":"))),
            )
        return int(result.lastrowid)

    def next_sequence(self, sensor_id: str) -> int:
        row = self.connection.execute(
            "SELECT sequence_number FROM sensor_sequences WHERE sensor_id = ?",
            (sensor_id,),
        ).fetchone()
        return int(row[0]) + 1 if row else 1

    def pending(self) -> list[tuple[int, str, int, dict[str, Any]]]:
        rows = self.connection.execute(
            """SELECT id, sensor_id, sequence_number, payload
               FROM pending_readings ORDER BY sensor_id, sequence_number"""
        ).fetchall()
        return [
            (int(row[0]), str(row[1]), int(row[2]), json.loads(row[3]))
            for row in rows
        ]

    def delete(self, row_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM pending_readings WHERE id = ?", (row_id,))

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM pending_readings").fetchone()
        return int(row[0])

    def close(self) -> None:
        self.connection.close()

