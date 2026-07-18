from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from config import R2_PUBLIC_URL, SUMITALK_CHAT_QUEUE_DB
from services.public_url import resolve_public_base_url


logger = logging.getLogger("sumitalk")

_OPEN_TAG = "<voice>"
_CLOSE_TAG = "</voice>"
_COMPLETE_VOICE_RE = re.compile(r"<voice>[\s\S]*?</voice>", flags=re.IGNORECASE)
_VOICE_SIDECAR_WORKERS = max(1, int(os.environ.get("SUMITALK_VOICE_SIDECAR_WORKERS", "2") or "2"))
_VOICE_SIDECAR_STALE_SECONDS = max(
    60.0,
    float(os.environ.get("SUMITALK_VOICE_SIDECAR_STALE_SECONDS", "300") or "300"),
)
_VOICE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_VOICE_SIDECAR_WORKERS,
    thread_name_prefix="sumitalk-voice-sidecar",
)
_STREAM_LOCK = threading.Lock()
_STREAMS: dict[tuple[str, str], "_VoiceStreamParser"] = {}


@dataclass(frozen=True)
class CompletedVoice:
    voice_index: int
    transcript: str


@dataclass(frozen=True)
class VoiceDeltaResult:
    visible_text: str
    completed: tuple[CompletedVoice, ...]


class _VoiceStreamParser:
    def __init__(self) -> None:
        self.buffer = ""
        self.inside_voice = False
        self.voice_text = ""
        self.next_voice_index = 0

    @staticmethod
    def _partial_tag_suffix(value: str, tag: str) -> int:
        lowered = value.lower()
        target = tag.lower()
        maximum = min(len(lowered), len(target) - 1)
        for size in range(maximum, 0, -1):
            if lowered.endswith(target[:size]):
                return size
        return 0

    def feed(self, text: str) -> VoiceDeltaResult:
        self.buffer += str(text or "")
        visible: list[str] = []
        completed: list[CompletedVoice] = []
        while self.buffer:
            tag = _CLOSE_TAG if self.inside_voice else _OPEN_TAG
            index = self.buffer.lower().find(tag)
            if index >= 0:
                prefix = self.buffer[:index]
                self.buffer = self.buffer[index + len(tag) :]
                if self.inside_voice:
                    self.voice_text += prefix
                    completed.append(
                        CompletedVoice(
                            voice_index=self.next_voice_index,
                            transcript=self.voice_text.strip(),
                        )
                    )
                    self.next_voice_index += 1
                    self.voice_text = ""
                    self.inside_voice = False
                else:
                    visible.append(prefix)
                    self.inside_voice = True
                continue

            held = self._partial_tag_suffix(self.buffer, tag)
            ready = self.buffer[:-held] if held else self.buffer
            self.buffer = self.buffer[-held:] if held else ""
            if self.inside_voice:
                self.voice_text += ready
            else:
                visible.append(ready)
            break
        return VoiceDeltaResult("".join(visible), tuple(completed))

    def finish(self) -> VoiceDeltaResult:
        if self.inside_voice:
            visible = _OPEN_TAG + self.voice_text + self.buffer
        else:
            visible = self.buffer
        self.buffer = ""
        self.voice_text = ""
        self.inside_voice = False
        return VoiceDeltaResult(visible, ())


def feed_sumitalk_voice_delta(job_id: str, part_id: str, text: str) -> VoiceDeltaResult:
    key = (str(job_id or "").strip(), str(part_id or "assistant-final").strip() or "assistant-final")
    with _STREAM_LOCK:
        parser = _STREAMS.setdefault(key, _VoiceStreamParser())
        return parser.feed(text)


def finish_sumitalk_voice_part(job_id: str, part_id: str) -> VoiceDeltaResult:
    key = (str(job_id or "").strip(), str(part_id or "assistant-final").strip() or "assistant-final")
    with _STREAM_LOCK:
        parser = _STREAMS.pop(key, None)
    return parser.finish() if parser is not None else VoiceDeltaResult("", ())


def discard_sumitalk_voice_stream(job_id: str) -> None:
    clean_job_id = str(job_id or "").strip()
    with _STREAM_LOCK:
        for key in [key for key in _STREAMS if key[0] == clean_job_id]:
            _STREAMS.pop(key, None)


def strip_complete_sumitalk_voice_tags(text: str) -> str:
    return _COMPLETE_VOICE_RE.sub("", str(text or ""))


def _connect() -> sqlite3.Connection:
    path_value = SUMITALK_CHAT_QUEUE_DB
    try:
        from services import sumitalk_chat_queue

        path_value = sumitalk_chat_queue.SUMITALK_CHAT_QUEUE_DB
    except Exception:
        pass
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sumitalk_chat_voice_sidecars (
                task_id TEXT NOT NULL UNIQUE,
                job_id TEXT NOT NULL,
                source_part_id TEXT NOT NULL,
                voice_index INTEGER NOT NULL,
                event_part_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                lease_token TEXT,
                locked_at REAL,
                media_id TEXT,
                remote_key TEXT,
                audio_url TEXT,
                mime TEXT,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                event_emitted INTEGER NOT NULL DEFAULT 0,
                event_seq INTEGER,
                event_lease_token TEXT,
                event_locked_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(job_id, source_part_id, voice_index)
            );
            CREATE INDEX IF NOT EXISTS idx_sumitalk_chat_voice_sidecars_job_status
                ON sumitalk_chat_voice_sidecars(job_id, status, event_emitted);
            """
        )


def _safe_source_part_id(part_id: str) -> str:
    return str(part_id or "assistant-final").strip()[:220] or "assistant-final"


def _voice_task_id(job_id: str, source_part_id: str, voice_index: int) -> str:
    raw = f"{job_id}\0{source_part_id}\0{voice_index}".encode("utf-8", errors="replace")
    return "sumitalk-voice-" + hashlib.sha256(raw).hexdigest()[:32]


def _event_part_id(source_part_id: str, voice_index: int) -> str:
    return f"{source_part_id}:voice:{voice_index}"


def _submit(function, *args) -> bool:
    try:
        _VOICE_EXECUTOR.submit(function, *args)
        return True
    except Exception:
        logger.exception("[SumiTalk] voice_sidecar_submit_failed")
        return False


def schedule_sumitalk_voice_sidecar(
    job_id: str,
    part_id: str,
    voice_index: int,
    transcript: str,
) -> str:
    clean_job_id = str(job_id or "").strip()
    source_part_id = _safe_source_part_id(part_id)
    clean_transcript = str(transcript or "").strip()
    index = max(0, int(voice_index or 0))
    if not re.fullmatch(r"[a-f0-9]{32}", clean_job_id) or not clean_transcript:
        return ""
    task_id = _voice_task_id(clean_job_id, source_part_id, index)
    now = time.time()
    lease_token = uuid4().hex
    claimed = False
    dispatch_needed = False
    _ensure_schema()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO sumitalk_chat_voice_sidecars
                    (task_id, job_id, source_part_id, voice_index, event_part_id,
                     transcript, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    task_id,
                    clean_job_id,
                    source_part_id,
                    index,
                    _event_part_id(source_part_id, index),
                    clean_transcript,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT transcript, status, event_emitted FROM sumitalk_chat_voice_sidecars WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is not None and str(row["transcript"] or "") != clean_transcript:
                logger.warning(
                    "[SumiTalk] voice_sidecar_transcript_conflict task_id=%s job_id=%s part_id=%s index=%s",
                    task_id,
                    clean_job_id,
                    source_part_id,
                    index,
                )
            status = str((row or {})["status"] or "") if row is not None else ""
            if status in {"ready", "failed"}:
                dispatch_needed = not bool(int((row or {})["event_emitted"] or 0))
            else:
                cursor = conn.execute(
                    """
                    UPDATE sumitalk_chat_voice_sidecars
                    SET status='processing', attempts=attempts+1, lease_token=?, locked_at=?, updated_at=?
                    WHERE task_id=?
                      AND (status='pending' OR (status='processing' AND COALESCE(locked_at, 0)<?))
                    """,
                    (lease_token, now, now, task_id, now - _VOICE_SIDECAR_STALE_SECONDS),
                )
                claimed = cursor.rowcount == 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    if claimed:
        if not _submit(_run_claimed_sidecar, task_id, lease_token):
            _release_processing_claim(task_id, lease_token)
    elif dispatch_needed:
        _submit(_dispatch_sidecar_event, task_id)
    return task_id


def _release_processing_claim(task_id: str, lease_token: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE sumitalk_chat_voice_sidecars
            SET status='pending', lease_token=NULL, locked_at=NULL, updated_at=?
            WHERE task_id=? AND status='processing' AND lease_token=?
            """,
            (time.time(), task_id, lease_token),
        )


def _tts_audio_bytes(transcript: str) -> bytes:
    from services.minimax_tts import tts_to_audio_bytes

    return bytes(tts_to_audio_bytes(transcript, audio_format="mp3") or b"")


def _upload_audio(audio_bytes: bytes, task_id: str) -> dict | None:
    from storage import r2_store

    return r2_store.upload_sumitalk_chat_media_file(
        "audio",
        f"{task_id}.mp3",
        audio_bytes,
        "audio/mpeg",
    )


def _audio_public_url(remote_key: str) -> str:
    key = str(remote_key or "").strip()
    route = f"/miniapp-api/chat-media/raw-public?key={quote(key, safe='/')}"
    base = resolve_public_base_url().rstrip("/")
    if base:
        return f"{base}{route}"
    r2_base = str(R2_PUBLIC_URL or "").strip().rstrip("/")
    return f"{r2_base}/{key.lstrip('/')}" if r2_base else route


def _wav_duration_ms(audio_bytes: bytes) -> int:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            rate = int(wav.getframerate() or 0)
            frames = int(wav.getnframes() or 0)
        return max(0, int(round(frames * 1000.0 / rate))) if rate > 0 else 0
    except Exception:
        return 0


def _mp3_frame_info(data: bytes, offset: int) -> tuple[int, int, int] | None:
    if offset + 4 > len(data):
        return None
    header = int.from_bytes(data[offset : offset + 4], "big")
    if (header >> 21) & 0x7FF != 0x7FF:
        return None
    version_bits = (header >> 19) & 0x3
    layer_bits = (header >> 17) & 0x3
    bitrate_index = (header >> 12) & 0xF
    sample_index = (header >> 10) & 0x3
    padding = (header >> 9) & 0x1
    if version_bits == 1 or layer_bits != 1 or bitrate_index in {0, 15} or sample_index == 3:
        return None
    if version_bits == 3:
        bitrates = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
        sample_rate = (44100, 48000, 32000)[sample_index]
        samples = 1152
        coefficient = 144
    else:
        bitrates = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
        divisor = 2 if version_bits == 2 else 4
        sample_rate = (44100, 48000, 32000)[sample_index] // divisor
        samples = 576
        coefficient = 72
    bitrate = bitrates[bitrate_index] * 1000
    frame_length = int(coefficient * bitrate / sample_rate) + padding
    return (frame_length, samples, sample_rate) if frame_length > 4 else None


def _mp3_duration_ms(audio_bytes: bytes) -> int:
    data = bytes(audio_bytes or b"")
    offset = 0
    if data.startswith(b"ID3") and len(data) >= 10:
        size_bytes = data[6:10]
        if all(value < 128 for value in size_bytes):
            offset = 10 + sum(value << shift for value, shift in zip(size_bytes, (21, 14, 7, 0)))
    frames = 0
    total_seconds = 0.0
    cursor = min(offset, len(data))
    while cursor + 4 <= len(data):
        info = _mp3_frame_info(data, cursor)
        if info is None:
            cursor += 1
            continue
        frame_length, samples, sample_rate = info
        if cursor + frame_length > len(data):
            break
        frames += 1
        total_seconds += samples / float(sample_rate)
        cursor += frame_length
    return max(0, int(round(total_seconds * 1000.0))) if frames else 0


def audio_duration_ms(audio_bytes: bytes, mime: str = "audio/mpeg") -> int:
    normalized = str(mime or "").strip().lower()
    if "wav" in normalized or bytes(audio_bytes or b"").startswith(b"RIFF"):
        return _wav_duration_ms(audio_bytes)
    return _mp3_duration_ms(audio_bytes)


def _complete_processing(
    task_id: str,
    lease_token: str,
    *,
    status: str,
    media_id: str = "",
    remote_key: str = "",
    audio_url: str = "",
    mime: str = "",
    duration_ms: int = 0,
    error: str = "",
) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE sumitalk_chat_voice_sidecars
            SET status=?, media_id=?, remote_key=?, audio_url=?, mime=?, duration_ms=?, error=?,
                lease_token=NULL, locked_at=NULL, event_emitted=0, event_seq=NULL,
                event_lease_token=NULL, event_locked_at=NULL, updated_at=?
            WHERE task_id=? AND status='processing' AND lease_token=?
            """,
            (
                status,
                media_id,
                remote_key,
                audio_url,
                mime,
                max(0, int(duration_ms or 0)),
                str(error or "")[:500],
                time.time(),
                task_id,
                lease_token,
            ),
        )
    return cursor.rowcount == 1


def _run_claimed_sidecar(task_id: str, lease_token: str) -> None:
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            "SELECT job_id, transcript FROM sumitalk_chat_voice_sidecars WHERE task_id=? AND lease_token=?",
            (task_id, lease_token),
        ).fetchone()
    if row is None:
        return
    job_id = str(row["job_id"] or "")
    transcript = str(row["transcript"] or "")
    try:
        audio_bytes = _tts_audio_bytes(transcript)
        if not audio_bytes:
            raise RuntimeError("tts_empty_audio")
        duration = audio_duration_ms(audio_bytes, "audio/mpeg")
        if duration <= 0:
            raise RuntimeError("audio_duration_unavailable")
        uploaded = _upload_audio(audio_bytes, task_id)
        if not uploaded:
            raise RuntimeError("audio_upload_failed")
        remote_key = str(uploaded.get("key") or "").strip()
        audio_url = _audio_public_url(remote_key)
        if not remote_key or not audio_url:
            raise RuntimeError("audio_url_unavailable")
        media_id = str(uploaded.get("id") or remote_key).strip()
        if not _complete_processing(
            task_id,
            lease_token,
            status="ready",
            media_id=media_id,
            remote_key=remote_key,
            audio_url=audio_url,
            mime="audio/mpeg",
            duration_ms=duration,
        ):
            return
        logger.info(
            "[SumiTalk] voice_sidecar_ready task_id=%s job_id=%s chars=%s duration_ms=%s",
            task_id,
            job_id,
            len(transcript),
            duration,
        )
    except Exception as exc:
        error = str(exc or "voice_sidecar_failed")[:500] or "voice_sidecar_failed"
        if not _complete_processing(task_id, lease_token, status="failed", error=error):
            return
        logger.warning(
            "[SumiTalk] voice_sidecar_failed task_id=%s job_id=%s error=%s",
            task_id,
            job_id,
            error,
            exc_info=True,
        )
    _dispatch_sidecar_event(task_id)


def _job_is_terminal(job_id: str) -> bool:
    from services.sumitalk_chat_queue import read_sumitalk_chat_job_state

    state = read_sumitalk_chat_job_state(job_id) or {}
    return str(state.get("status") or "").strip().lower() in {"done", "error", "cancelled"}


def _existing_sidecar_event(job_id: str, task_id: str) -> dict | None:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event_json
            FROM sumitalk_chat_run_events
            WHERE job_id=? AND kind IN ('assistant_audio_ready', 'assistant_audio_failed')
            ORDER BY seq DESC
            """,
            (job_id,),
        ).fetchall()
    for row in rows:
        try:
            event = json.loads(str(row["event_json"] or "{}"))
        except Exception:
            continue
        if isinstance(event, dict) and str(event.get("sidecar_task_id") or "") == task_id:
            return event
    return None


def _claim_event_dispatch(task_id: str) -> sqlite3.Row | None:
    lease_token = uuid4().hex
    now = time.time()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = conn.execute(
                """
                UPDATE sumitalk_chat_voice_sidecars
                SET event_lease_token=?, event_locked_at=?, updated_at=?
                WHERE task_id=? AND status IN ('ready', 'failed') AND event_emitted=0
                  AND (event_lease_token IS NULL OR COALESCE(event_locked_at, 0)<?)
                """,
                (lease_token, now, now, task_id, now - _VOICE_SIDECAR_STALE_SECONDS),
            )
            row = conn.execute(
                "SELECT * FROM sumitalk_chat_voice_sidecars WHERE task_id=?",
                (task_id,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    if cursor.rowcount != 1 or row is None:
        return None
    return row


def _release_event_dispatch(task_id: str, lease_token: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE sumitalk_chat_voice_sidecars
            SET event_lease_token=NULL, event_locked_at=NULL, updated_at=?
            WHERE task_id=? AND event_emitted=0 AND event_lease_token=?
            """,
            (time.time(), task_id, lease_token),
        )


def _dispatch_sidecar_event(task_id: str) -> None:
    row = _claim_event_dispatch(task_id)
    if row is None:
        return
    lease_token = str(row["event_lease_token"] or "")
    job_id = str(row["job_id"] or "")
    if not _job_is_terminal(job_id):
        _release_event_dispatch(task_id, lease_token)
        if _job_is_terminal(job_id):
            _submit(_dispatch_sidecar_event, task_id)
        return
    try:
        from services.realtime_publish import publish_sumitalk_chat_event
        from services.sumitalk_chat_queue import (
            append_sumitalk_chat_job_event,
            flush_sumitalk_chat_live_events,
            read_sumitalk_chat_job_state,
        )

        if not flush_sumitalk_chat_live_events(timeout=5.0):
            raise RuntimeError("live_event_flush_timeout")
        event_kind = "assistant_audio_ready" if str(row["status"] or "") == "ready" else "assistant_audio_failed"
        payload = {
            "job_id": job_id,
            "part_id": str(row["event_part_id"] or ""),
            "source_part_id": str(row["source_part_id"] or ""),
            "voice_index": int(row["voice_index"] or 0),
            "transcript": str(row["transcript"] or ""),
            "sidecar_task_id": task_id,
        }
        if event_kind == "assistant_audio_ready":
            payload.update(
                {
                    "media_id": str(row["media_id"] or ""),
                    "remote_key": str(row["remote_key"] or ""),
                    "audio_url": str(row["audio_url"] or ""),
                    "mime": str(row["mime"] or "audio/mpeg"),
                    "duration_ms": int(row["duration_ms"] or 0),
                }
            )
        else:
            payload["error"] = str(row["error"] or "voice_sidecar_failed")
        event = _existing_sidecar_event(job_id, task_id)
        if event is None:
            event = append_sumitalk_chat_job_event(job_id, event_kind, payload)
        if event is None:
            raise RuntimeError("sidecar_event_append_failed")
        with _connect() as conn:
            conn.execute(
                """
                UPDATE sumitalk_chat_voice_sidecars
                SET event_emitted=1, event_seq=?, event_lease_token=NULL, event_locked_at=NULL, updated_at=?
                WHERE task_id=? AND event_lease_token=?
                """,
                (int(event.get("seq") or 0), time.time(), task_id, lease_token),
            )
        state = read_sumitalk_chat_job_state(job_id) or {}
        try:
            publish_sumitalk_chat_event(
                str(state.get("reply_target") or ""),
                event,
                window_id=str(state.get("window_id") or ""),
            )
        except Exception:
            logger.debug(
                "[SumiTalk] voice_sidecar_realtime_publish_failed task_id=%s",
                task_id,
                exc_info=True,
            )
    except Exception:
        _release_event_dispatch(task_id, lease_token)
        logger.exception("[SumiTalk] voice_sidecar_event_failed task_id=%s job_id=%s", task_id, job_id)


def notify_sumitalk_voice_job_terminal(job_id: str) -> None:
    clean_job_id = str(job_id or "").strip()
    if clean_job_id:
        _submit(_dispatch_completed_sidecars, clean_job_id)


def _dispatch_completed_sidecars(job_id: str) -> None:
    _ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT task_id
            FROM sumitalk_chat_voice_sidecars
            WHERE job_id=? AND status IN ('ready', 'failed') AND event_emitted=0
            ORDER BY voice_index ASC
            """,
            (job_id,),
        ).fetchall()
    for row in rows:
        _dispatch_sidecar_event(str(row["task_id"] or ""))


def resume_sumitalk_voice_sidecars(job_id: str) -> None:
    clean_job_id = str(job_id or "").strip()
    if not clean_job_id:
        return
    _ensure_schema()
    now = time.time()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT task_id
            FROM sumitalk_chat_voice_sidecars
            WHERE job_id=? AND (
                status='pending'
                OR (status='processing' AND COALESCE(locked_at, 0)<?)
                OR (status IN ('ready', 'failed') AND event_emitted=0)
            )
            ORDER BY voice_index ASC
            """,
            (clean_job_id, now - _VOICE_SIDECAR_STALE_SECONDS),
        ).fetchall()
    for row in rows:
        task_id = str(row["task_id"] or "")
        with _connect() as conn:
            current = conn.execute(
                """
                SELECT source_part_id, voice_index, transcript, status
                FROM sumitalk_chat_voice_sidecars
                WHERE task_id=?
                """,
                (task_id,),
            ).fetchone()
        if current is None:
            continue
        if str(current["status"] or "") in {"ready", "failed"}:
            _submit(_dispatch_sidecar_event, task_id)
            continue
        schedule_sumitalk_voice_sidecar(
            clean_job_id,
            str(current["source_part_id"] or ""),
            int(current["voice_index"] or 0),
            str(current["transcript"] or ""),
        )


def pending_sumitalk_voice_sidecar_count(job_id: str) -> int:
    clean_job_id = str(job_id or "").strip()
    if not clean_job_id:
        return 0
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM sumitalk_chat_voice_sidecars
            WHERE job_id=? AND (
                status IN ('pending', 'processing')
                OR (status IN ('ready', 'failed') AND event_emitted=0)
            )
            """,
            (clean_job_id,),
        ).fetchone()
    return int((row or {})["n"] or 0) if row else 0


def cleanup_sumitalk_voice_sidecars(cutoff_ts: float) -> None:
    _ensure_schema()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM sumitalk_chat_voice_sidecars WHERE updated_at<?",
            (float(cutoff_ts or 0),),
        )


def get_sumitalk_voice_sidecar(task_id: str) -> dict | None:
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sumitalk_chat_voice_sidecars WHERE task_id=?",
            (str(task_id or "").strip(),),
        ).fetchone()
    return dict(row) if row is not None else None
