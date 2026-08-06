from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime

from config import EVENT_CLAIM_IDLE_MS
from runtime.events import (
    EventEnvelope,
    SUMITALK_CHAT_JOB_CREATED,
    TELEGRAM_WEBHOOK_JOB_CREATED,
)
from runtime.outbox import (
    OutboxSource,
    ensure_outbox_schema,
    event_exists_for_job,
    insert_outbox_event,
    outbox_sources,
)


@dataclass(frozen=True)
class ReconcileResult:
    created_events: int = 0
    reset_stale_jobs: int = 0
    scheduled_republish: int = 0


def reconcile_event_sources() -> ReconcileResult:
    totals = ReconcileResult()
    for source in outbox_sources():
        current = _reconcile_source(source)
        totals = ReconcileResult(
            created_events=totals.created_events + current.created_events,
            reset_stale_jobs=totals.reset_stale_jobs + current.reset_stale_jobs,
            scheduled_republish=totals.scheduled_republish + current.scheduled_republish,
        )
    return totals


def _reconcile_source(source: OutboxSource) -> ReconcileResult:
    if source.name == "sumitalk":
        return _reconcile_sumitalk(source)
    if source.name == "telegram":
        return _reconcile_telegram(source)
    return ReconcileResult()


def _reconcile_sumitalk(source: OutboxSource) -> ReconcileResult:
    from runtime.outbox import connect_source
    from services.sumitalk_chat_queue import _ensure_schema

    _ensure_schema()
    cutoff = time.time() - max(30.0, EVENT_CLAIM_IDLE_MS / 1000.0)
    cutoff_iso = datetime.fromtimestamp(cutoff).astimezone().isoformat(timespec="seconds")
    created = 0
    reset = 0
    republish = 0
    with connect_source(source) as conn:
        ensure_outbox_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            stale_job_ids = {
                str(row["job_id"] or "")
                for row in conn.execute(
                    """
                    SELECT job_id
                    FROM sumitalk_chat_jobs
                    WHERE status='processing'
                      AND (locked_at IS NULL OR locked_at<?)
                    """,
                    (cutoff,),
                ).fetchall()
            }
            reset = int(
                conn.execute(
                    """
                    UPDATE sumitalk_chat_jobs
                    SET status='pending', locked_at=NULL, lease_token=NULL,
                        updated_at=?, last_error='event runtime recovered stale lease'
                    WHERE status='processing'
                      AND (locked_at IS NULL OR locked_at<?)
                    """,
                    (time.time(), cutoff),
                ).rowcount
                or 0
            )
            rows = conn.execute(
                """
                SELECT job_id, request_key, payload_json, created_at, updated_at
                FROM sumitalk_chat_jobs
                WHERE status IN ('pending', 'processing')
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            for row in rows:
                job_id = str(row["job_id"] or "")
                if not event_exists_for_job(conn, job_id):
                    try:
                        payload = json.loads(str(row["payload_json"] or "{}"))
                    except Exception:
                        payload = {}
                    chat_body = payload.get("chat_body") if isinstance(payload, dict) else {}
                    if not isinstance(chat_body, dict):
                        chat_body = {}
                    event = EventEnvelope.create(
                        SUMITALK_CHAT_JOB_CREATED,
                        job_id=job_id,
                        partition_key=str(chat_body.get("window_id") or job_id),
                        payload={
                            "request_key": str(row["request_key"] or ""),
                            "window_id": str(chat_body.get("window_id") or ""),
                            "reconciled": True,
                        },
                    )
                    insert_outbox_event(conn, event, aggregate_type="sumitalk_chat_job")
                    created += 1
                elif job_id in stale_job_ids or float(row["updated_at"] or 0) < cutoff:
                    republish += _schedule_job_republish(conn, job_id, published_before=cutoff_iso)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return ReconcileResult(created, reset, republish)


def _reconcile_telegram(source: OutboxSource) -> ReconcileResult:
    from runtime.outbox import connect_source
    from services.telegram_update_queue import _ensure_schema

    _ensure_schema()
    cutoff = time.time() - max(30.0, EVENT_CLAIM_IDLE_MS / 1000.0)
    cutoff_iso = datetime.fromtimestamp(cutoff).astimezone().isoformat(timespec="seconds")
    created = 0
    reset = 0
    republish = 0
    with connect_source(source) as conn:
        ensure_outbox_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            stale_update_keys = {
                str(row["update_key"] or "")
                for row in conn.execute(
                    """
                    SELECT update_key
                    FROM telegram_webhook_updates
                    WHERE status='processing'
                      AND (locked_at IS NULL OR locked_at<?)
                    """,
                    (cutoff,),
                ).fetchall()
            }
            reset = int(
                conn.execute(
                    """
                    UPDATE telegram_webhook_updates
                    SET status='pending', locked_at=NULL, lease_token=NULL,
                        updated_at=?, last_error='event runtime recovered stale lease'
                    WHERE status='processing'
                      AND (locked_at IS NULL OR locked_at<?)
                    """,
                    (time.time(), cutoff),
                ).rowcount
                or 0
            )
            rows = conn.execute(
                """
                SELECT update_key, bot_kind, update_json, created_at, updated_at
                FROM telegram_webhook_updates
                WHERE status IN ('pending', 'processing')
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            for row in rows:
                update_key = str(row["update_key"] or "")
                if not event_exists_for_job(conn, update_key):
                    try:
                        update = json.loads(str(row["update_json"] or "{}"))
                    except Exception:
                        update = {}
                    from services.telegram_update_queue import telegram_update_partition_key

                    bot_kind = str(row["bot_kind"] or "main")
                    event = EventEnvelope.create(
                        TELEGRAM_WEBHOOK_JOB_CREATED,
                        job_id=update_key,
                        partition_key=telegram_update_partition_key(update, bot_kind),
                        payload={
                            "bot_kind": bot_kind,
                            "update_key": update_key,
                            "reconciled": True,
                        },
                    )
                    insert_outbox_event(conn, event, aggregate_type="telegram_webhook_update")
                    created += 1
                elif update_key in stale_update_keys or float(row["updated_at"] or 0) < cutoff:
                    republish += _schedule_job_republish(
                        conn,
                        update_key,
                        published_before=cutoff_iso,
                    )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return ReconcileResult(created, reset, republish)


def _schedule_job_republish(conn, job_id: str, *, published_before: str) -> int:
    cur = conn.execute(
        """
        UPDATE outbox_events
        SET published_at=NULL, next_attempt_at=NULL, last_error='reconciler scheduled republish'
        WHERE event_id=(
            SELECT event_id
            FROM outbox_events
            WHERE aggregate_id=?
              AND published_at IS NOT NULL
              AND published_at<=?
            ORDER BY created_at DESC, event_id DESC
            LIMIT 1
        )
        """,
        (str(job_id or ""), str(published_before or "")),
    )
    return int(cur.rowcount or 0)
