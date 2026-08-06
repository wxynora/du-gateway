from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from config import (
    EVENT_CONSUMER_GROUP_INTERACTIVE,
    EVENT_OUTBOX_FALLBACK_SCAN_SECONDS,
    EVENT_RUNTIME_ENABLED,
    EVENT_STREAM_INTERACTIVE,
)
from runtime.events import EventEnvelope
from runtime.outbox import outbox_metrics
from runtime.redis_streams import RedisStreams
from storage.runtime_sqlite import connect
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing


REQUIRED_COMPONENTS = ("event-dispatcher", "interactive-worker")


def record_heartbeat(
    component: str,
    *,
    consumer_name: str = "",
    details: Mapping[str, Any] | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO event_runtime_heartbeats (
                component, consumer_name, updated_at, details_json
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(component) DO UPDATE SET
                consumer_name=excluded.consumer_name,
                updated_at=excluded.updated_at,
                details_json=excluded.details_json
            """,
            (
                str(component or "").strip(),
                str(consumer_name or "").strip(),
                now_beijing_iso(),
                json.dumps(dict(details or {}), ensure_ascii=False, separators=(",", ":")),
            ),
        )


def heartbeat_snapshot(*, stale_after_seconds: float | None = None) -> dict[str, Any]:
    threshold = float(
        stale_after_seconds
        if stale_after_seconds is not None
        else max(90.0, EVENT_OUTBOX_FALLBACK_SCAN_SECONDS * 3.0)
    )
    now = datetime.now().astimezone()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT component, consumer_name, updated_at, details_json
            FROM event_runtime_heartbeats
            ORDER BY component
            """
        ).fetchall()
    snapshot: dict[str, Any] = {}
    for row in rows:
        updated = parse_iso_to_beijing(str(row["updated_at"] or ""))
        age = max(0.0, (now - updated).total_seconds()) if updated is not None else None
        try:
            details = json.loads(str(row["details_json"] or "{}"))
        except Exception:
            details = {}
        snapshot[str(row["component"])] = {
            "consumer_name": str(row["consumer_name"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "age_seconds": round(age, 3) if age is not None else None,
            "fresh": age is not None and age <= threshold,
            "details": details if isinstance(details, dict) else {},
        }
    return snapshot


def record_dead_letter(
    event: EventEnvelope,
    *,
    stream_message_id: str,
    consumer: str,
    delivery_count: int,
    error: str,
) -> None:
    safe_error = str(error or "").replace("\r", " ").replace("\n", " ").strip()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO dead_letter_events (
                event_id, stream_message_id, event_type, job_id, partition_key,
                trace_id, payload_json, consumer, delivery_count, error, failed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, stream_message_id) DO UPDATE SET
                consumer=excluded.consumer,
                delivery_count=excluded.delivery_count,
                error=excluded.error,
                failed_at=excluded.failed_at
            """,
            (
                event.event_id,
                str(stream_message_id or ""),
                event.type,
                event.job_id,
                event.partition_key,
                event.trace_id,
                event.to_json(),
                str(consumer or ""),
                max(0, int(delivery_count)),
                safe_error,
                now_beijing_iso(),
            ),
        )


def dead_letter_count() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM dead_letter_events").fetchone()
    return int(row["n"] or 0) if row else 0


def event_runtime_health() -> dict[str, Any]:
    if not EVENT_RUNTIME_ENABLED:
        return {"enabled": False, "live": True, "ready": True}

    errors: list[str] = []
    redis_ok = False
    pending = 0
    streams: RedisStreams | None = None
    try:
        streams = RedisStreams.from_url()
        redis_ok = streams.ping()
        summary = streams.pending_summary(
            EVENT_STREAM_INTERACTIVE,
            EVENT_CONSUMER_GROUP_INTERACTIVE,
        )
        pending = int(summary.get("pending", 0) or 0)
    except Exception as exc:
        errors.append(f"redis: {type(exc).__name__}: {exc}")
    finally:
        if streams is not None:
            streams.close()

    try:
        outbox = outbox_metrics()
    except Exception as exc:
        outbox = {"unpublished": None, "oldest_unpublished_age_seconds": None, "sources": {}}
        errors.append(f"outbox: {type(exc).__name__}: {exc}")

    try:
        heartbeats = heartbeat_snapshot()
        dead_letters = dead_letter_count()
    except Exception as exc:
        heartbeats = {}
        dead_letters = None
        errors.append(f"runtime_sqlite: {type(exc).__name__}: {exc}")

    components_ready = all(
        bool(heartbeats.get(component, {}).get("fresh"))
        for component in REQUIRED_COMPONENTS
    )
    return {
        "enabled": True,
        "live": True,
        "ready": bool(redis_ok and components_ready and not errors),
        "redis": {"ok": redis_ok},
        "stream": EVENT_STREAM_INTERACTIVE,
        "consumer_group": EVENT_CONSUMER_GROUP_INTERACTIVE,
        "pending": pending,
        "outbox": outbox,
        "heartbeats": heartbeats,
        "dead_letters": dead_letters,
        "errors": errors,
    }
