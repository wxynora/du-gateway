from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from config import SUMITALK_CHAT_QUEUE_DB, TELEGRAM_WEBHOOK_QUEUE_DB
from runtime.events import EventEnvelope
from utils.time_aware import now_beijing_iso


OUTBOX_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL,
    aggregate_type TEXT,
    aggregate_id TEXT,
    partition_key TEXT,
    trace_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    publish_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_attempt_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_events_published_at
    ON outbox_events(published_at);
CREATE INDEX IF NOT EXISTS idx_outbox_events_next_attempt_at
    ON outbox_events(next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_outbox_events_created_at
    ON outbox_events(created_at);
CREATE INDEX IF NOT EXISTS idx_outbox_events_aggregate_id
    ON outbox_events(aggregate_id);
"""

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboxSource:
    name: str
    db_path: Path


@dataclass(frozen=True)
class OutboxRecord:
    source: OutboxSource
    event: EventEnvelope
    publish_attempts: int
    source_sequence: int


def outbox_sources() -> tuple[OutboxSource, ...]:
    return (
        OutboxSource("sumitalk", Path(SUMITALK_CHAT_QUEUE_DB)),
        OutboxSource("telegram", Path(TELEGRAM_WEBHOOK_QUEUE_DB)),
    )


def connect_source(source: OutboxSource) -> sqlite3.Connection:
    source.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(source.db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_outbox_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(OUTBOX_SCHEMA_SQL)


def initialize_outbox_schemas(sources: Iterable[OutboxSource] | None = None) -> None:
    for source in sources or outbox_sources():
        with connect_source(source) as conn:
            ensure_outbox_schema(conn)


def notify_outbox_dispatcher(source: str) -> bool:
    streams = None
    try:
        from runtime.redis_streams import RedisStreams

        streams = RedisStreams.from_url()
        streams.publish_wakeup(str(source or "outbox"))
        return True
    except Exception as exc:
        logger.warning(
            "event outbox wakeup unavailable source=%s error=%s: %s",
            source,
            type(exc).__name__,
            exc,
        )
        return False
    finally:
        if streams is not None:
            streams.close()


def insert_outbox_event(
    conn: sqlite3.Connection,
    event: EventEnvelope,
    *,
    aggregate_type: str,
) -> None:
    conn.execute(
        """
        INSERT INTO outbox_events (
            event_id, event_type, event_version, aggregate_type, aggregate_id,
            partition_key, trace_id, payload_json, created_at, published_at,
            publish_attempts, last_error, next_attempt_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL)
        """,
        (
            event.event_id,
            event.type,
            event.version,
            str(aggregate_type or "").strip(),
            event.job_id,
            event.partition_key,
            event.trace_id,
            event.to_json(),
            event.created_at,
        ),
    )


def fetch_due_outbox(
    source: OutboxSource,
    *,
    limit: int,
    now_iso: str | None = None,
) -> list[OutboxRecord]:
    with connect_source(source) as conn:
        ensure_outbox_schema(conn)
        rows = conn.execute(
            """
            SELECT current.rowid AS source_sequence,
                   current.payload_json,
                   current.publish_attempts
            FROM outbox_events AS current
            WHERE current.published_at IS NULL
              AND (current.next_attempt_at IS NULL OR current.next_attempt_at <= ?)
              AND NOT EXISTS (
                  SELECT 1
                  FROM outbox_events AS earlier
                  WHERE earlier.published_at IS NULL
                    AND COALESCE(earlier.partition_key, '') = COALESCE(current.partition_key, '')
                    AND earlier.rowid < current.rowid
              )
            ORDER BY current.rowid ASC
            LIMIT ?
            """,
            (str(now_iso or now_beijing_iso()), max(1, int(limit))),
        ).fetchall()
    return [
        OutboxRecord(
            source=source,
            event=EventEnvelope.from_json(str(row["payload_json"] or "")),
            publish_attempts=int(row["publish_attempts"] or 0),
            source_sequence=int(row["source_sequence"] or 0),
        )
        for row in rows
    ]


def mark_outbox_published(source: OutboxSource, event_id: str, *, published_at: str | None = None) -> bool:
    with connect_source(source) as conn:
        ensure_outbox_schema(conn)
        cur = conn.execute(
            """
            UPDATE outbox_events
            SET published_at=?, next_attempt_at=NULL, last_error=NULL
            WHERE event_id=? AND published_at IS NULL
            """,
            (str(published_at or now_beijing_iso()), str(event_id or "")),
        )
    return int(cur.rowcount or 0) > 0


def mark_outbox_publish_failed(
    source: OutboxSource,
    event_id: str,
    *,
    error: str,
    next_attempt_at: str,
) -> int:
    safe_error = str(error or "").replace("\r", " ").replace("\n", " ").strip()
    with connect_source(source) as conn:
        ensure_outbox_schema(conn)
        conn.execute(
            """
            UPDATE outbox_events
            SET publish_attempts=publish_attempts+1, last_error=?, next_attempt_at=?
            WHERE event_id=? AND published_at IS NULL
            """,
            (safe_error, str(next_attempt_at or ""), str(event_id or "")),
        )
        row = conn.execute(
            "SELECT publish_attempts FROM outbox_events WHERE event_id=?",
            (str(event_id or ""),),
        ).fetchone()
    return int(row["publish_attempts"] or 0) if row else 0


def outbox_metrics(sources: Iterable[OutboxSource] | None = None) -> dict[str, object]:
    total = 0
    oldest: datetime | None = None
    per_source: dict[str, int] = {}
    now = datetime.now().astimezone()
    for source in sources or outbox_sources():
        with connect_source(source) as conn:
            ensure_outbox_schema(conn)
            row = conn.execute(
                """
                SELECT COUNT(*) AS n, MIN(created_at) AS oldest
                FROM outbox_events
                WHERE published_at IS NULL
                """
            ).fetchone()
        count = int(row["n"] or 0) if row else 0
        per_source[source.name] = count
        total += count
        raw_oldest = str(row["oldest"] or "") if row else ""
        if raw_oldest:
            try:
                candidate = datetime.fromisoformat(raw_oldest)
                if candidate.tzinfo is None:
                    candidate = candidate.replace(tzinfo=now.tzinfo)
                if oldest is None or candidate < oldest:
                    oldest = candidate
            except Exception:
                pass
    age = max(0.0, (now - oldest).total_seconds()) if oldest is not None else 0.0
    return {
        "unpublished": total,
        "oldest_unpublished_age_seconds": round(age, 3),
        "sources": per_source,
    }


def load_outbox_event(source: OutboxSource, event_id: str) -> EventEnvelope | None:
    with connect_source(source) as conn:
        ensure_outbox_schema(conn)
        row = conn.execute(
            "SELECT payload_json FROM outbox_events WHERE event_id=?",
            (str(event_id or ""),),
        ).fetchone()
    return EventEnvelope.from_json(str(row["payload_json"] or "")) if row else None


def event_exists_for_job(conn: sqlite3.Connection, job_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM outbox_events WHERE aggregate_id=? LIMIT 1",
        (str(job_id or ""),),
    ).fetchone()
    return row is not None


def latest_outbox_for_job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT event_id, created_at, published_at
        FROM outbox_events
        WHERE aggregate_id=?
        ORDER BY created_at DESC, event_id DESC
        LIMIT 1
        """,
        (str(job_id or ""),),
    ).fetchone()
