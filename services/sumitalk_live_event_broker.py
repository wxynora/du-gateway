from __future__ import annotations

import asyncio
import time
from collections import deque


class SumiTalkRunEventBroker:
    """Process-local live fan-out; SQLite remains the reconnect source of truth."""

    def __init__(self, *, max_events_per_job: int = 512, ttl_seconds: float = 1800.0) -> None:
        self._condition = asyncio.Condition()
        self._events: dict[str, deque[dict]] = {}
        self._updated_at: dict[str, float] = {}
        self._max_events_per_job = max(32, int(max_events_per_job))
        self._ttl_seconds = max(60.0, float(ttl_seconds))

    async def publish(self, event: dict) -> bool:
        job_id = str((event or {}).get("job_id") or (event or {}).get("run_id") or "").strip()
        try:
            seq = int((event or {}).get("seq") or 0)
        except Exception:
            seq = 0
        if not job_id or seq <= 0:
            return False

        row = dict(event)
        now = time.monotonic()
        async with self._condition:
            events = self._events.setdefault(job_id, deque(maxlen=self._max_events_per_job))
            if not any(int(existing.get("seq") or 0) == seq for existing in events):
                events.append(row)
            self._updated_at[job_id] = now
            cutoff = now - self._ttl_seconds
            for stale_job_id in [key for key, touched in self._updated_at.items() if touched < cutoff]:
                self._events.pop(stale_job_id, None)
                self._updated_at.pop(stale_job_id, None)
            self._condition.notify_all()
        return True

    async def subscribe(self, job_id: str, after_seq: int, *, heartbeat_seconds: float = 10.0):
        cursor = max(0, int(after_seq or 0))
        while True:
            timed_out = False
            async with self._condition:
                available = [
                    dict(event)
                    for event in self._events.get(job_id, ())
                    if int(event.get("seq") or 0) > cursor
                ]
                if not available:
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=max(1.0, heartbeat_seconds))
                    except asyncio.TimeoutError:
                        timed_out = True
                    available = [
                        dict(event)
                        for event in self._events.get(job_id, ())
                        if int(event.get("seq") or 0) > cursor
                    ]
            if not available:
                if timed_out:
                    yield None
                continue
            for event in sorted(available, key=lambda item: int(item.get("seq") or 0)):
                seq = int(event.get("seq") or 0)
                if seq <= cursor:
                    continue
                cursor = seq
                yield event
