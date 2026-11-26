from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pika
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dlq


class FakeChannel:
    def __init__(self):
        self.messages = []
        self.published = []
        self.acked = []

    def queue_declare(self, *, queue, passive=False):
        return SimpleNamespace(method=SimpleNamespace(message_count=2, consumer_count=0))

    def queue_purge(self, *, queue):
        return SimpleNamespace(method=SimpleNamespace(message_count=2))

    def confirm_delivery(self):
        return None

    def basic_get(self, *, queue, auto_ack):
        if not self.messages:
            return None, None, None
        return self.messages.pop(0)

    def basic_publish(self, **kwargs):
        self.published.append(kwargs)
        return True

    def basic_ack(self, *, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, *, delivery_tag, requeue):
        raise AssertionError("no se esperaba basic_nack")


class FakeConnection:
    def __init__(self, channel):
        self._channel = channel
        self.is_open = True

    def channel(self):
        return self._channel

    def close(self):
        self.is_open = False


def _setup(monkeypatch, channel):
    connection = FakeConnection(channel)
    monkeypatch.setattr(dlq, "connect", lambda url: connection)
    monkeypatch.setattr(dlq, "declare_topology", lambda active: None)
    monkeypatch.setattr(dlq, "work_queue_names", lambda: ("integration.sample",))
    return connection


def test_list_reports_dlq_depth_and_messages(monkeypatch, capsys):
    channel = FakeChannel()
    _setup(monkeypatch, channel)
    item = {"payload": "bad message"}
    monkeypatch.setattr(dlq, "_list_messages", lambda *args, **kwargs: [item])

    assert dlq.run("list", "integration.sample") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["queue"] == "integration.sample.dlq"
    assert result["messages_ready"] == 2
    assert result["items"] == [item]


def test_replay_resets_attempt_and_acks_only_after_publish(monkeypatch, capsys):
    channel = FakeChannel()
    _setup(monkeypatch, channel)
    properties = pika.BasicProperties(
        message_id="message-1",
        correlation_id="correlation-1",
        headers={"x-attempt": 2, "x-error": "previous failure"},
    )
    body = b'{"event_id":"message-1"}'
    channel.messages.append((SimpleNamespace(delivery_tag=7), properties, body))

    assert dlq.run("replay", "integration.sample") == 0
    assert channel.acked == [7]
    assert len(channel.published) == 1
    replay = channel.published[0]
    assert replay["routing_key"] == "integration.sample"
    assert replay["body"] == body
    assert replay["properties"].headers == {"x-attempt": 0}
    assert replay["properties"].message_id == "message-1"
    assert "Se reenviaron 1 mensajes" in capsys.readouterr().out


def test_purge_reports_number_of_removed_messages(monkeypatch, capsys):
    channel = FakeChannel()
    _setup(monkeypatch, channel)

    assert dlq.run("purge", "integration.sample") == 0
    assert "Se eliminaron 2 mensajes" in capsys.readouterr().out


def test_unknown_queue_is_rejected_before_connecting(monkeypatch):
    monkeypatch.setattr(dlq, "work_queue_names", lambda: ("known.queue",))
    monkeypatch.setattr(dlq, "connect", lambda url: pytest.fail("no debe conectar"))

    with pytest.raises(ValueError, match="Cola desconocida"):
        dlq.run("purge", "unknown.queue")
