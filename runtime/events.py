from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from utils.time_aware import now_beijing_iso


SUMITALK_CHAT_JOB_CREATED = "sumitalk.chat_job.created"
TELEGRAM_WEBHOOK_JOB_CREATED = "telegram.webhook_job.created"
SUPPORTED_EVENT_TYPES = frozenset(
    {
        SUMITALK_CHAT_JOB_CREATED,
        TELEGRAM_WEBHOOK_JOB_CREATED,
    }
)
_EVENT_TYPE_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")


class EventValidationError(ValueError):
    pass


def _required_text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise EventValidationError(f"missing event field: {name}")
    return text


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    type: str
    version: int
    job_id: str
    partition_key: str
    trace_id: str
    created_at: str
    payload: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("event_id", "type", "job_id", "partition_key", "trace_id", "created_at"):
            _required_text(name, getattr(self, name))
        if int(self.version) != 1:
            raise EventValidationError(f"unsupported event version: {self.version!r}")
        if not _EVENT_TYPE_RE.fullmatch(self.type):
            raise EventValidationError(f"invalid event type: {self.type!r}")
        if not isinstance(self.payload, dict):
            raise EventValidationError("event payload must be an object")

    @classmethod
    def create(
        cls,
        event_type: str,
        *,
        job_id: str,
        partition_key: str,
        trace_id: str = "",
        payload: Mapping[str, Any] | None = None,
        event_id: str = "",
        created_at: str = "",
    ) -> "EventEnvelope":
        return cls(
            event_id=str(event_id or uuid4()),
            type=str(event_type or "").strip(),
            version=1,
            job_id=str(job_id or "").strip(),
            partition_key=str(partition_key or "").strip(),
            trace_id=str(trace_id or uuid4()),
            created_at=str(created_at or now_beijing_iso()),
            payload=dict(payload or {}),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EventEnvelope":
        if not isinstance(data, Mapping):
            raise EventValidationError("event envelope must be an object")
        known = {
            "event_id",
            "type",
            "version",
            "job_id",
            "partition_key",
            "trace_id",
            "created_at",
            "payload",
        }
        try:
            version = int(data.get("version", 0))
        except Exception as exc:
            raise EventValidationError("event version must be an integer") from exc
        payload = data.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload or "{}")
            except Exception as exc:
                raise EventValidationError("event payload is not valid JSON") from exc
        return cls(
            event_id=_required_text("event_id", data.get("event_id")),
            type=_required_text("type", data.get("type")),
            version=version,
            job_id=_required_text("job_id", data.get("job_id")),
            partition_key=_required_text("partition_key", data.get("partition_key")),
            trace_id=_required_text("trace_id", data.get("trace_id")),
            created_at=_required_text("created_at", data.get("created_at")),
            payload=payload,
            extra={str(key): value for key, value in data.items() if key not in known},
        )

    @classmethod
    def from_json(cls, raw: str) -> "EventEnvelope":
        try:
            data = json.loads(str(raw or ""))
        except Exception as exc:
            raise EventValidationError("event envelope is not valid JSON") from exc
        return cls.from_dict(data)

    @classmethod
    def from_stream_fields(cls, fields: Mapping[Any, Any]) -> "EventEnvelope":
        normalized: dict[str, Any] = {}
        for key, value in fields.items():
            if isinstance(key, bytes):
                key = key.decode("utf-8", "replace")
            if isinstance(value, bytes):
                value = value.decode("utf-8", "replace")
            normalized[str(key)] = value
        if normalized.get("event_json"):
            return cls.from_json(str(normalized["event_json"]))
        if "payload_json" in normalized and "payload" not in normalized:
            normalized["payload"] = normalized.pop("payload_json")
        return cls.from_dict(normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra,
            "event_id": self.event_id,
            "type": self.type,
            "version": self.version,
            "job_id": self.job_id,
            "partition_key": self.partition_key,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "payload": dict(self.payload),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def to_stream_fields(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "version": str(self.version),
            "job_id": self.job_id,
            "partition_key": self.partition_key,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "payload_json": json.dumps(self.payload, ensure_ascii=False, separators=(",", ":")),
        }
