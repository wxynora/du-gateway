from __future__ import annotations

import logging
import socket
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from config import (
    EVENT_BLOCK_MS,
    EVENT_CLAIM_IDLE_MS,
    EVENT_CONSUMER_GROUP_INTERACTIVE,
    EVENT_CONSUMER_NAME,
    EVENT_INTERACTIVE_MAX_WORKERS,
    EVENT_MAX_DELIVERY_ATTEMPTS,
    EVENT_STREAM_INTERACTIVE,
    SUMITALK_CHAT_QUEUE_STALE_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_WEBHOOK_QUEUE_MAX_ATTEMPTS,
    TELEGRAM_WEBHOOK_QUEUE_STALE_SECONDS,
)
from runtime.events import (
    EventEnvelope,
    SUMITALK_CHAT_JOB_CREATED,
    SUPPORTED_EVENT_TYPES,
    TELEGRAM_WEBHOOK_JOB_CREATED,
)
from runtime.health import record_dead_letter, record_heartbeat
from runtime.redis_streams import RedisStreams, StreamMessage


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingResult:
    status: str
    detail: str = ""

    @property
    def successful(self) -> bool:
        return self.status in {"processed", "noop"}


class InteractiveEventHandlers:
    def __init__(self, flask_app: Any) -> None:
        self.flask_app = flask_app

    def initialize(self) -> None:
        from services.telegram_bot import init_telegram_bot_runtime

        init_telegram_bot_runtime()

    def process(self, event: EventEnvelope) -> ProcessingResult:
        if event.type == SUMITALK_CHAT_JOB_CREATED:
            return self._process_sumitalk(event)
        if event.type == TELEGRAM_WEBHOOK_JOB_CREATED:
            return self._process_telegram(event)
        raise ValueError(f"unsupported interactive event type: {event.type}")

    def dead_letter(self, event: EventEnvelope, error: str) -> None:
        if event.type == SUMITALK_CHAT_JOB_CREATED:
            from services.sumitalk_chat_queue import dead_letter_sumitalk_chat_job

            dead_letter_sumitalk_chat_job(event.job_id, error)
        elif event.type == TELEGRAM_WEBHOOK_JOB_CREATED:
            from services.telegram_update_queue import dead_letter_update

            dead_letter_update(event.job_id, error)

    def _process_sumitalk(self, event: EventEnvelope) -> ProcessingResult:
        from services.sumitalk_chat_queue import (
            _TERMINAL_JOB_STATUSES,
            ack_sumitalk_chat_queue_item,
            claim_sumitalk_chat_job,
            is_sumitalk_chat_job_cancelled,
            read_sumitalk_chat_job_state,
            release_sumitalk_chat_queue_item,
            run_sumitalk_chat_job,
        )

        item = claim_sumitalk_chat_job(
            event.job_id,
            stale_after_seconds=SUMITALK_CHAT_QUEUE_STALE_SECONDS,
        )
        if item is None:
            state = read_sumitalk_chat_job_state(event.job_id) or {}
            status = str(state.get("status") or "").strip().lower()
            if status in _TERMINAL_JOB_STATUSES:
                return ProcessingResult("noop", f"terminal:{status}")
            raise RuntimeError(f"SumiTalk job is not claimable: {event.job_id}")

        if is_sumitalk_chat_job_cancelled(item.job_id):
            if not ack_sumitalk_chat_queue_item(item.id, lease_token=item.lease_token):
                raise RuntimeError(f"SumiTalk cancelled job lease lost: {item.job_id}")
            return ProcessingResult("noop", "cancelled")

        try:
            status = run_sumitalk_chat_job(
                self.flask_app,
                item.job_id,
                item.payload,
                queue_id=item.id,
                lease_token=item.lease_token,
            )
            if status == "stale_lease":
                raise RuntimeError(f"SumiTalk job lease lost: {item.job_id}")
            if not ack_sumitalk_chat_queue_item(item.id, lease_token=item.lease_token):
                raise RuntimeError(f"SumiTalk job ack lost lease: {item.job_id}")
            return ProcessingResult("processed", status)
        except Exception as exc:
            release_sumitalk_chat_queue_item(
                item.id,
                str(exc),
                lease_token=item.lease_token,
            )
            raise

    def _process_telegram(self, event: EventEnvelope) -> ProcessingResult:
        from services.telegram_bot import handle_telegram_update
        from services.telegram_update_queue import (
            ack_update,
            claim_update_by_key,
            fail_update,
            get_update_status,
        )

        max_attempts = max(int(TELEGRAM_WEBHOOK_QUEUE_MAX_ATTEMPTS or 8), 1)
        item = claim_update_by_key(
            event.job_id,
            stale_after_seconds=TELEGRAM_WEBHOOK_QUEUE_STALE_SECONDS,
            max_attempts=max_attempts,
        )
        if item is None:
            current = get_update_status(event.job_id)
            if current is not None and current[0] == "dead":
                raise RuntimeError(
                    f"Telegram queue job exhausted attempts: {event.job_id} attempts={current[1]}"
                )
            return ProcessingResult("noop", "queue row absent or already terminal")
        if item.bot_kind != "main":
            if not ack_update(item.id, lease_token=item.lease_token):
                raise RuntimeError(f"Telegram obsolete job lease lost: {item.update_key}")
            return ProcessingResult("noop", "obsolete bot kind")

        token = str(TELEGRAM_BOT_TOKEN or "").strip()
        if not token:
            fail_update(
                item.id,
                "missing main bot token",
                max_attempts=max_attempts,
                lease_token=item.lease_token,
            )
            raise RuntimeError("missing main Telegram bot token")
        try:
            handle_telegram_update(item.update, bot_token=token)
            if not ack_update(item.id, lease_token=item.lease_token):
                raise RuntimeError(f"Telegram job ack lost lease: {item.update_key}")
            return ProcessingResult("processed", item.update_key)
        except Exception as exc:
            fail_update(
                item.id,
                str(exc),
                max_attempts=max_attempts,
                lease_token=item.lease_token,
            )
            raise


class KeyedExecutor:
    def __init__(self, max_workers: int) -> None:
        self.max_workers = max(1, int(max_workers))
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="interactive-event",
        )
        self._condition = threading.Condition()
        self._active: set[str] = set()
        self._queued: dict[str, deque[Callable[[], None]]] = {}
        self._inflight = 0

    @property
    def inflight(self) -> int:
        with self._condition:
            return self._inflight

    def wait_for_capacity(self, stop_event: threading.Event) -> int:
        with self._condition:
            while self._inflight >= self.max_workers and not stop_event.is_set():
                self._condition.wait(timeout=0.5)
            return max(0, self.max_workers - self._inflight)

    def submit(self, partition_key: str, task: Callable[[], None]) -> None:
        key = str(partition_key or "")
        with self._condition:
            if self._inflight >= self.max_workers:
                raise RuntimeError("keyed executor capacity exhausted")
            self._inflight += 1
            if key in self._active:
                self._queued.setdefault(key, deque()).append(task)
                return
            self._active.add(key)
        self._executor.submit(self._run, key, task)

    def _run(self, key: str, task: Callable[[], None]) -> None:
        try:
            task()
        except Exception:
            logger.exception("interactive event task escaped partition=%s", key)
        next_task: Callable[[], None] | None = None
        with self._condition:
            self._inflight -= 1
            queue = self._queued.get(key)
            if queue:
                next_task = queue.popleft()
                if not queue:
                    self._queued.pop(key, None)
            else:
                self._active.discard(key)
            self._condition.notify_all()
        if next_task is not None:
            self._executor.submit(self._run, key, next_task)

    def shutdown(self) -> None:
        with self._condition:
            while self._inflight > 0:
                self._condition.wait(timeout=0.5)
        self._executor.shutdown(wait=True, cancel_futures=False)


class InteractiveStreamWorker:
    def __init__(
        self,
        streams: RedisStreams,
        handlers: InteractiveEventHandlers,
        *,
        stream_name: str = EVENT_STREAM_INTERACTIVE,
        group_name: str = EVENT_CONSUMER_GROUP_INTERACTIVE,
        consumer_name: str,
        max_workers: int = EVENT_INTERACTIVE_MAX_WORKERS,
    ) -> None:
        self.streams = streams
        self.handlers = handlers
        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.scheduler = KeyedExecutor(max_workers)
        self._own_pending_cursor = "0-0"
        self._recovering_own_pending = True
        self._claim_cursor = "0-0"
        self._next_claim_at = 0.0

    def run(self, stop_event: threading.Event) -> None:
        self.streams.ensure_group(self.stream_name, self.group_name)
        claim_interval = max(5.0, min(60.0, EVENT_CLAIM_IDLE_MS / 2000.0))
        try:
            while not stop_event.is_set():
                capacity = self.scheduler.wait_for_capacity(stop_event)
                if capacity <= 0:
                    continue
                messages: list[StreamMessage]
                now_mono = time.monotonic()
                if self._recovering_own_pending:
                    messages = self.streams.read_pending(
                        stream=self.stream_name,
                        group=self.group_name,
                        consumer=self.consumer_name,
                        start_id=self._own_pending_cursor,
                        count=capacity,
                    )
                    if messages:
                        self._own_pending_cursor = messages[-1].message_id
                    else:
                        self._recovering_own_pending = False
                elif now_mono >= self._next_claim_at:
                    self._claim_cursor, messages, _deleted = self.streams.autoclaim(
                        stream=self.stream_name,
                        group=self.group_name,
                        consumer=self.consumer_name,
                        min_idle_ms=EVENT_CLAIM_IDLE_MS,
                        start_id=self._claim_cursor,
                        count=capacity,
                    )
                    self._next_claim_at = (
                        now_mono if self._claim_cursor != "0-0" else now_mono + claim_interval
                    )
                else:
                    messages = []
                if not messages:
                    messages = self.streams.read_group(
                        stream=self.stream_name,
                        group=self.group_name,
                        consumer=self.consumer_name,
                        count=capacity,
                        block_ms=EVENT_BLOCK_MS,
                    )
                for message in messages:
                    try:
                        event = EventEnvelope.from_stream_fields(message.fields)
                        partition_key = event.partition_key
                    except Exception:
                        event = None
                        partition_key = f"invalid:{message.message_id}"
                    self.scheduler.submit(
                        partition_key,
                        lambda current=message, parsed=event: self._handle_message(current, parsed),
                    )
                self._heartbeat(last_error="")
        finally:
            self.scheduler.shutdown()

    def _handle_message(
        self,
        message: StreamMessage,
        event: EventEnvelope | None,
    ) -> None:
        started = time.monotonic()
        if event is None:
            invalid = EventEnvelope.create(
                "runtime.invalid_event",
                job_id=message.message_id,
                partition_key=f"invalid:{message.message_id}",
                payload={"stream_fields": message.fields},
            )
            self._dead_letter(message, invalid, 1, "invalid event envelope")
            return
        if event.type not in SUPPORTED_EVENT_TYPES:
            self._dead_letter(message, event, 1, f"unsupported event type: {event.type}")
            return

        deliveries = max(
            1,
            self.streams.delivery_count(
                self.stream_name,
                self.group_name,
                message.message_id,
            ),
        )
        if deliveries > EVENT_MAX_DELIVERY_ATTEMPTS:
            self._dead_letter(message, event, deliveries, "delivery attempts exhausted")
            return
        try:
            result = self.handlers.process(event)
            if not result.successful:
                raise RuntimeError(result.detail or result.status)
            self.streams.ack(self.stream_name, self.group_name, message.message_id)
            logger.info(
                "interactive_event_result event_id=%s event_type=%s job_id=%s trace_id=%s "
                "partition_key=%s stream=%s consumer_group=%s consumer=%s delivery_count=%s "
                "queue_delay_ms=%s processing_ms=%s result=%s",
                event.event_id,
                event.type,
                event.job_id,
                event.trace_id,
                event.partition_key,
                self.stream_name,
                self.group_name,
                self.consumer_name,
                deliveries,
                _queue_delay_ms(event),
                int((time.monotonic() - started) * 1000),
                result.status,
            )
        except Exception as exc:
            deliveries = max(
                deliveries,
                self.streams.delivery_count(
                    self.stream_name,
                    self.group_name,
                    message.message_id,
                ),
            )
            if deliveries >= EVENT_MAX_DELIVERY_ATTEMPTS:
                self._dead_letter(
                    message,
                    event,
                    deliveries,
                    f"{type(exc).__name__}: {exc}",
                )
            else:
                logger.warning(
                    "interactive_event_result event_id=%s event_type=%s job_id=%s trace_id=%s "
                    "partition_key=%s stream=%s consumer_group=%s consumer=%s delivery_count=%s "
                    "queue_delay_ms=%s processing_ms=%s result=retry error_type=%s error=%s",
                    event.event_id,
                    event.type,
                    event.job_id,
                    event.trace_id,
                    event.partition_key,
                    self.stream_name,
                    self.group_name,
                    self.consumer_name,
                    deliveries,
                    _queue_delay_ms(event),
                    int((time.monotonic() - started) * 1000),
                    type(exc).__name__,
                    exc,
                )

    def _dead_letter(
        self,
        message: StreamMessage,
        event: EventEnvelope,
        deliveries: int,
        error: str,
    ) -> None:
        record_dead_letter(
            event,
            stream_message_id=message.message_id,
            consumer=self.consumer_name,
            delivery_count=deliveries,
            error=error,
        )
        self.handlers.dead_letter(event, error)
        self.streams.ack(self.stream_name, self.group_name, message.message_id)
        logger.error(
            "interactive_event_result event_id=%s event_type=%s job_id=%s trace_id=%s "
            "partition_key=%s stream=%s consumer_group=%s consumer=%s delivery_count=%s "
            "queue_delay_ms=%s result=dead_letter error=%s",
            event.event_id,
            event.type,
            event.job_id,
            event.trace_id,
            event.partition_key,
            self.stream_name,
            self.group_name,
            self.consumer_name,
            deliveries,
            _queue_delay_ms(event),
            error,
        )

    def _heartbeat(self, *, last_error: str) -> None:
        record_heartbeat(
            "interactive-worker",
            consumer_name=self.consumer_name,
            details={
                "inflight": self.scheduler.inflight,
                "last_error": str(last_error or ""),
            },
        )


def default_consumer_name() -> str:
    configured = str(EVENT_CONSUMER_NAME or "").strip()
    if configured:
        return configured
    return socket.gethostname()


def _queue_delay_ms(event: EventEnvelope) -> int:
    try:
        created = datetime.fromisoformat(event.created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return max(0, int((datetime.now().astimezone() - created).total_seconds() * 1000))
    except Exception:
        return 0


def run_interactive_worker(flask_app, stop_event: threading.Event) -> None:
    handlers = InteractiveEventHandlers(flask_app)
    handlers.initialize()
    consumer_name = default_consumer_name()
    while not stop_event.is_set():
        streams: RedisStreams | None = None
        try:
            streams = RedisStreams.from_url(
                socket_timeout_seconds=(EVENT_BLOCK_MS / 1000.0) + 1.0
            )
            InteractiveStreamWorker(
                streams,
                handlers,
                consumer_name=consumer_name,
            ).run(stop_event)
        except Exception as exc:
            logger.exception("interactive stream worker connection failed")
            try:
                record_heartbeat(
                    "interactive-worker",
                    consumer_name=consumer_name,
                    details={"inflight": 0, "last_error": f"{type(exc).__name__}: {exc}"},
                )
            except Exception:
                logger.exception("interactive worker heartbeat failed")
            stop_event.wait(2.0)
        finally:
            if streams is not None:
                streams.close()
