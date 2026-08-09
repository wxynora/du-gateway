from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from config import EVENT_REDIS_CONNECT_TIMEOUT_SECONDS, REDIS_URL
from runtime.events import EventEnvelope


WAKEUP_CHANNEL = "du:outbox:wakeup"


class RedisRuntimeUnavailable(RuntimeError):
    pass


def _redis_module():
    try:
        import redis
    except ImportError as exc:
        raise RedisRuntimeUnavailable(
            "redis-py is required by Event Runtime"
        ) from exc
    return redis


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


@dataclass(frozen=True)
class StreamMessage:
    message_id: str
    fields: dict[str, str]


class RedisStreams:
    def __init__(self, client: Any) -> None:
        self.client = client

    @classmethod
    def from_url(
        cls,
        url: str | None = None,
        *,
        socket_timeout_seconds: float | None = None,
    ) -> "RedisStreams":
        redis = _redis_module()
        socket_timeout = max(
            EVENT_REDIS_CONNECT_TIMEOUT_SECONDS,
            float(socket_timeout_seconds or EVENT_REDIS_CONNECT_TIMEOUT_SECONDS),
        )
        client = redis.Redis.from_url(
            str(url or REDIS_URL),
            decode_responses=True,
            socket_connect_timeout=EVENT_REDIS_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=socket_timeout,
            health_check_interval=30,
        )
        return cls(client)

    def ping(self) -> bool:
        return bool(self.client.ping())

    def ensure_group(self, stream: str, group: str) -> None:
        redis = _redis_module()
        try:
            self.client.xgroup_create(stream, group, id="0-0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def publish_event(self, stream: str, event: EventEnvelope) -> str:
        return _text(self.client.xadd(stream, event.to_stream_fields()))

    def publish_wakeup(self, source: str) -> int:
        return int(self.client.publish(WAKEUP_CHANNEL, str(source or "outbox")))

    def read_group(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> list[StreamMessage]:
        response = self.client.xreadgroup(
            group,
            consumer,
            {stream: ">"},
            count=max(1, int(count)),
            block=max(1, int(block_ms)),
        )
        return _normalize_read_response(response)

    def read_pending(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        start_id: str,
        count: int,
    ) -> list[StreamMessage]:
        response = self.client.xreadgroup(
            group,
            consumer,
            {stream: str(start_id or "0-0")},
            count=max(1, int(count)),
        )
        return _normalize_read_response(response)

    def ack(self, stream: str, group: str, *message_ids: str) -> int:
        ids = tuple(str(item) for item in message_ids if str(item or ""))
        return int(self.client.xack(stream, group, *ids)) if ids else 0

    def pending_summary(self, stream: str, group: str) -> dict[str, Any]:
        raw = self.client.xpending(stream, group)
        if isinstance(raw, Mapping):
            return {str(key): value for key, value in raw.items()}
        if isinstance(raw, (list, tuple)) and raw:
            return {"pending": int(raw[0] or 0)}
        return {"pending": 0}

    def delivery_count(self, stream: str, group: str, message_id: str) -> int:
        rows = self.client.xpending_range(
            stream,
            group,
            min=message_id,
            max=message_id,
            count=1,
        )
        if not rows:
            return 0
        row = rows[0]
        if isinstance(row, Mapping):
            for key in ("times_delivered", b"times_delivered"):
                if key in row:
                    return int(row[key] or 0)
        if isinstance(row, (list, tuple)) and len(row) >= 4:
            return int(row[3] or 0)
        return 0

    def autoclaim(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        min_idle_ms: int,
        start_id: str = "0-0",
        count: int = 100,
    ) -> tuple[str, list[StreamMessage], list[str]]:
        response = self.client.xautoclaim(
            stream,
            group,
            consumer,
            min_idle_time=max(1, int(min_idle_ms)),
            start_id=start_id,
            count=max(1, int(count)),
        )
        if not isinstance(response, (list, tuple)) or len(response) < 2:
            return "0-0", [], []
        next_id = _text(response[0])
        messages = _normalize_messages(response[1])
        deleted = [_text(item) for item in response[2]] if len(response) >= 3 else []
        return next_id, messages, deleted

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()


class OutboxWakeSubscriber:
    def __init__(self, streams: RedisStreams) -> None:
        self._pubsub = streams.client.pubsub(ignore_subscribe_messages=True)
        self._pubsub.subscribe(WAKEUP_CHANNEL)

    def wait(self, timeout_seconds: float) -> str | None:
        message = self._pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=max(0.0, float(timeout_seconds)),
        )
        if not message:
            return None
        return _text(message.get("data", ""))

    def close(self) -> None:
        self._pubsub.close()


def _normalize_read_response(response: Any) -> list[StreamMessage]:
    messages: list[StreamMessage] = []
    for stream_entry in response or []:
        if not isinstance(stream_entry, (list, tuple)) or len(stream_entry) < 2:
            continue
        messages.extend(_normalize_messages(stream_entry[1]))
    return messages


def _normalize_messages(raw_messages: Any) -> list[StreamMessage]:
    messages: list[StreamMessage] = []
    for raw in raw_messages or []:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        raw_fields = raw[1] if isinstance(raw[1], Mapping) else {}
        fields = {_text(key): _text(value) for key, value in raw_fields.items()}
        messages.append(StreamMessage(message_id=_text(raw[0]), fields=fields))
    return messages
