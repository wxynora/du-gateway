from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Iterable
from typing import Any

from runtime.redis_streams import RedisStreams


logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "du:runtime:wakeup:"
_TOPIC_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")
_PUBLISHER_LOCK = threading.RLock()
_PUBLISHER: RedisStreams | None = None


def _topic(value: str) -> str:
    return _TOPIC_RE.sub("-", str(value or "").strip()).strip("-")[:160]


def _channel(topic: str) -> str:
    clean = _topic(topic)
    if not clean:
        raise ValueError("runtime wakeup topic is required")
    return f"{_CHANNEL_PREFIX}{clean}"


def publish_runtime_wakeup(topic: str, payload: Any = None) -> bool:
    """Best-effort wake signal; durable stores remain the source of truth."""
    global _PUBLISHER
    try:
        body = json.dumps(
            {"topic": _topic(topic), "payload": payload, "ts": time.time()},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        with _PUBLISHER_LOCK:
            if _PUBLISHER is None:
                _PUBLISHER = RedisStreams.from_url(socket_timeout_seconds=1.0)
            _PUBLISHER.client.publish(_channel(topic), body)
        return True
    except Exception as exc:
        logger.debug("runtime wakeup publish failed topic=%s error=%s", topic, exc)
        with _PUBLISHER_LOCK:
            if _PUBLISHER is not None:
                _PUBLISHER.close()
            _PUBLISHER = None
        return False


class RuntimeWakeSubscriber:
    def __init__(self, topics: str | Iterable[str], *, socket_timeout_seconds: float = 65.0) -> None:
        raw_topics = [topics] if isinstance(topics, str) else list(topics)
        self.topics = tuple(dict.fromkeys(_topic(item) for item in raw_topics if _topic(item)))
        if not self.topics:
            raise ValueError("at least one runtime wakeup topic is required")
        self.socket_timeout_seconds = max(1.0, float(socket_timeout_seconds))
        self._streams: RedisStreams | None = None
        self._pubsub = None
        self._connect()

    @property
    def available(self) -> bool:
        return self._pubsub is not None

    def _connect(self) -> None:
        self.close()
        try:
            streams = RedisStreams.from_url(socket_timeout_seconds=self.socket_timeout_seconds)
            pubsub = streams.client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(*(_channel(topic) for topic in self.topics))
            self._streams = streams
            self._pubsub = pubsub
        except Exception as exc:
            logger.debug("runtime wakeup subscribe failed topics=%s error=%s", self.topics, exc)
            self.close()

    def wait(self, timeout_seconds: float) -> dict | None:
        timeout = max(0.0, float(timeout_seconds))
        if self._pubsub is None:
            if timeout > 0:
                time.sleep(timeout)
            self._connect()
            return None
        try:
            message = self._pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=timeout,
            )
        except Exception as exc:
            logger.debug("runtime wakeup wait failed topics=%s error=%s", self.topics, exc)
            self.close()
            return None
        if not message:
            return None
        raw = message.get("data")
        try:
            payload = json.loads(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or ""))
        except Exception:
            payload = {"payload": raw}
        return payload if isinstance(payload, dict) else {"payload": payload}

    def close(self) -> None:
        if self._pubsub is not None:
            try:
                self._pubsub.close()
            except Exception:
                pass
        self._pubsub = None
        if self._streams is not None:
            self._streams.close()
        self._streams = None

    def __enter__(self) -> "RuntimeWakeSubscriber":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
