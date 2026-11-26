"""Inspect, replay or purge a consumer's dead-letter queue."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from common.rabbit import (
    _publish_raw_to_queue,
    connect,
    dead_letter_queue_name,
    declare_topology,
    work_queue_names,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("list", "replay", "purge"),
        help="operación a realizar sobre la DLQ",
    )
    parser.add_argument("queue", help="nombre de la cola de trabajo, sin sufijo .dlq")
    parser.add_argument("--url", help="URL de RabbitMQ (por defecto RABBITMQ_URL)")
    parser.add_argument(
        "--limit", type=int, default=100,
        help="máximo de mensajes para replay (por defecto: 100)",
    )
    return parser


def _list_messages(dlq: str, *, url: str | None, limit: int) -> list[dict]:
    amqp_url = url or os.getenv(
        "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F"
    )
    parsed = urlsplit(amqp_url)
    management_url = os.getenv("RABBITMQ_MANAGEMENT_URL")
    if not management_url:
        host = parsed.hostname or "localhost"
        management_url = f"http://{host}:{os.getenv('RABBITMQ_MANAGEMENT_PORT', '15672')}"
    virtual_host = unquote(parsed.path.lstrip("/")) or "/"
    encoded_vhost = quote(virtual_host, safe="")
    username = unquote(parsed.username or "guest")
    password = unquote(parsed.password or "guest")
    auth = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    endpoint = (
        f"{management_url.rstrip('/')}/api/queues/{encoded_vhost}/{quote(dlq, safe='')}/get"
    )
    request = Request(
        endpoint,
        data=json.dumps({
            "count": limit,
            "ackmode": "ack_requeue_true",
            "encoding": "auto",
            "truncate": 50_000,
        }).encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        messages = json.loads(response.read())
    return messages


def run(action: str, queue: str, *, url: str | None = None, limit: int = 100) -> int:
    if queue not in work_queue_names():
        raise ValueError(f"Cola desconocida: {queue}")
    if limit < 1:
        raise ValueError("--limit debe ser mayor que 0")

    dlq = dead_letter_queue_name(queue)
    connection = connect(url)
    try:
        channel = connection.channel()
        declare_topology(channel)
        if action == "list":
            state = channel.queue_declare(queue=dlq, passive=True).method
            print(json.dumps({
                "queue": dlq,
                "messages_ready": state.message_count,
                "consumers": state.consumer_count,
                "items": _list_messages(dlq, url=url, limit=limit),
            }, ensure_ascii=False))
            return 0

        if action == "purge":
            count = channel.queue_purge(queue=dlq).method.message_count
            print(f"Se eliminaron {count} mensajes de {dlq}.")
            return 0

        replayed = 0
        while replayed < limit:
            method, properties, body = channel.basic_get(queue=dlq, auto_ack=False)
            if method is None:
                break
            headers = dict(properties.headers or {})
            headers["x-attempt"] = 0
            headers.pop("x-error", None)
            try:
                _publish_raw_to_queue(channel, queue, body, properties, headers)
            except Exception:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                raise
            channel.basic_ack(delivery_tag=method.delivery_tag)
            replayed += 1

        print(f"Se reenviaron {replayed} mensajes a {queue}.")
        return 0
    finally:
        if connection.is_open:
            connection.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args.action, args.queue, url=args.url, limit=args.limit)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
