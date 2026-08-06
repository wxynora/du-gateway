from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Iterable

from config import (
    EVENT_OUTBOX_BATCH_SIZE,
    EVENT_OUTBOX_FALLBACK_SCAN_SECONDS,
    EVENT_OUTBOX_MAX_RETRY_SECONDS,
    EVENT_STREAM_INTERACTIVE,
)
from runtime.health import record_heartbeat
from runtime.outbox import (
    OutboxRecord,
    OutboxSource,
    fetch_due_outbox,
    initialize_outbox_schemas,
    mark_outbox_publish_failed,
    mark_outbox_published,
    outbox_sources,
)
from runtime.reconciler import ReconcileResult, reconcile_event_sources
from runtime.redis_streams import OutboxWakeSubscriber, RedisStreams


logger = logging.getLogger(__name__)


class EventDispatcher:
    def __init__(
        self,
        streams: RedisStreams,
        *,
        sources: Iterable[OutboxSource] | None = None,
        stream_name: str = EVENT_STREAM_INTERACTIVE,
        batch_size: int = EVENT_OUTBOX_BATCH_SIZE,
    ) -> None:
        self.streams = streams
        self.sources = tuple(sources or outbox_sources())
        self.stream_name = str(stream_name)
        self.batch_size = max(1, int(batch_size))

    def dispatch_once(self) -> dict[str, int]:
        published = 0
        failed = 0
        examined = 0
        while examined < self.batch_size:
            due: list[OutboxRecord] = []
            remaining = self.batch_size - examined
            for source in self.sources:
                due.extend(fetch_due_outbox(source, limit=remaining))
            due.sort(
                key=lambda row: (
                    row.event.created_at,
                    row.source.name,
                    row.source_sequence,
                )
            )
            if not due:
                break
            for record in due[:remaining]:
                examined += 1
                started = time.monotonic()
                try:
                    self.streams.publish_event(self.stream_name, record.event)
                    if mark_outbox_published(record.source, record.event.event_id):
                        published += 1
                    logger.info(
                        "outbox_dispatch_result event_id=%s event_type=%s job_id=%s trace_id=%s "
                        "partition_key=%s stream=%s source=%s publish_attempt=%s queue_delay_ms=%s "
                        "processing_ms=%s result=published",
                        record.event.event_id,
                        record.event.type,
                        record.event.job_id,
                        record.event.trace_id,
                        record.event.partition_key,
                        self.stream_name,
                        record.source.name,
                        record.publish_attempts + 1,
                        _queue_delay_ms(record.event.created_at),
                        int((time.monotonic() - started) * 1000),
                    )
                except Exception as exc:
                    failed += 1
                    delay = min(
                        EVENT_OUTBOX_MAX_RETRY_SECONDS,
                        max(1.0, float(2 ** min(record.publish_attempts, 6))),
                    )
                    retry_at = (datetime.now().astimezone() + timedelta(seconds=delay)).isoformat(
                        timespec="seconds"
                    )
                    mark_outbox_publish_failed(
                        record.source,
                        record.event.event_id,
                        error=f"{type(exc).__name__}: {exc}",
                        next_attempt_at=retry_at,
                    )
                    logger.warning(
                        "outbox_dispatch_result event_id=%s event_type=%s job_id=%s trace_id=%s "
                        "partition_key=%s stream=%s source=%s publish_attempt=%s queue_delay_ms=%s "
                        "processing_ms=%s result=retry error_type=%s error=%s",
                        record.event.event_id,
                        record.event.type,
                        record.event.job_id,
                        record.event.trace_id,
                        record.event.partition_key,
                        self.stream_name,
                        record.source.name,
                        record.publish_attempts + 1,
                        _queue_delay_ms(record.event.created_at),
                        int((time.monotonic() - started) * 1000),
                        type(exc).__name__,
                        exc,
                    )
        return {"due": examined, "published": published, "failed": failed}


def run_dispatcher(stop_event: threading.Event) -> None:
    initialize_outbox_schemas()
    fallback = max(1.0, float(EVENT_OUTBOX_FALLBACK_SCAN_SECONDS))
    last_reconcile = 0.0
    while not stop_event.is_set():
        streams: RedisStreams | None = None
        subscriber: OutboxWakeSubscriber | None = None
        dispatch_result = {"due": 0, "published": 0, "failed": 0}
        reconcile_result = ReconcileResult()
        error = ""
        try:
            streams = RedisStreams.from_url(socket_timeout_seconds=fallback + 1.0)
            now_mono = time.monotonic()
            if now_mono - last_reconcile >= fallback:
                reconcile_result = reconcile_event_sources()
                last_reconcile = now_mono
            dispatch_result = EventDispatcher(streams).dispatch_once()
            subscriber = OutboxWakeSubscriber(streams)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("event dispatcher cycle failed: %s", error)
        try:
            record_heartbeat(
                "event-dispatcher",
                details={
                    **dispatch_result,
                    "reconciled_events": reconcile_result.created_events,
                    "recovered_jobs": reconcile_result.reset_stale_jobs,
                    "scheduled_republish": reconcile_result.scheduled_republish,
                    "last_error": error,
                },
            )
        except Exception:
            logger.exception("event dispatcher heartbeat failed")

        try:
            if subscriber is not None:
                subscriber.wait(fallback)
            else:
                stop_event.wait(fallback)
        except Exception as exc:
            logger.warning("event dispatcher wake subscription failed: %s", exc)
            stop_event.wait(min(fallback, 2.0))
        finally:
            if subscriber is not None:
                subscriber.close()
            if streams is not None:
                streams.close()


def _queue_delay_ms(created_at: str) -> int:
    try:
        created = datetime.fromisoformat(str(created_at or "").replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return max(0, int((datetime.now().astimezone() - created).total_seconds() * 1000))
    except Exception:
        return 0
