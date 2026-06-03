import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from config import TELEGRAM_WEBHOOK_QUEUE_DB
from utils.log import get_logger

logger = get_logger(__name__)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
_BOT_KINDS = {"main"}


@dataclass(frozen=True)
class EnqueueResult:
    enqueued: bool
    duplicate: bool
    update_key: str


@dataclass(frozen=True)
class QueuedTelegramUpdate:
    id: int
    bot_kind: str
    update_key: str
    update: dict
    attempts: int


def _db_path() -> Path:
    return Path(TELEGRAM_WEBHOOK_QUEUE_DB)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS telegram_webhook_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    update_key TEXT NOT NULL UNIQUE,
                    bot_kind TEXT NOT NULL,
                    update_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    locked_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tg_webhook_status_created
                    ON telegram_webhook_updates(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_tg_webhook_locked
                    ON telegram_webhook_updates(status, locked_at);
                """
            )
        _SCHEMA_READY = True


def _normalize_bot_kind(bot_kind: str) -> str:
    kind = (bot_kind or "").strip().lower()
    if kind not in _BOT_KINDS:
        raise ValueError(f"unsupported telegram bot kind: {bot_kind!r}")
    return kind


def make_update_key(update: dict, bot_kind: str) -> str:
    kind = _normalize_bot_kind(bot_kind)
    update_id = (update or {}).get("update_id") if isinstance(update, dict) else None
    if update_id is None:
        return f"{kind}:no-update-id:{uuid4().hex}"
    return f"{kind}:{update_id}"


def summarize_update(update: dict) -> str:
    update = update or {}
    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    from_user = msg.get("from") or {}
    text = (msg.get("text") or msg.get("caption") or "").strip()
    return (
        f"update_id={update.get('update_id')} "
        f"keys={','.join(sorted(update.keys()))} "
        f"chat_id={chat.get('id')} chat_type={chat.get('type')} "
        f"user_id={from_user.get('id')} "
        f"has_message={bool(msg)} has_text={bool(text)} text_len={len(text)} "
        f"has_photo={bool(msg.get('photo'))} has_document={bool(msg.get('document'))} "
        f"has_callback={bool(update.get('callback_query'))}"
    )


def enqueue_update(update: dict, bot_kind: str) -> EnqueueResult:
    _ensure_schema()
    kind = _normalize_bot_kind(bot_kind)
    clean_update = update if isinstance(update, dict) else {}
    update_key = make_update_key(clean_update, kind)
    now = time.time()
    payload = json.dumps(clean_update, ensure_ascii=False, separators=(",", ":"))
    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO telegram_webhook_updates
                    (update_key, bot_kind, update_json, status, attempts, locked_at, created_at, updated_at, last_error)
                VALUES (?, ?, ?, 'pending', 0, NULL, ?, ?, NULL)
                """,
                (update_key, kind, payload, now, now),
            )
            return EnqueueResult(enqueued=True, duplicate=False, update_key=update_key)
        except sqlite3.IntegrityError:
            return EnqueueResult(enqueued=False, duplicate=True, update_key=update_key)


def claim_next_update(
    *,
    stale_after_seconds: float = 300.0,
    max_attempts: int = 8,
) -> QueuedTelegramUpdate | None:
    _ensure_schema()
    now = time.time()
    stale_before = now - max(float(stale_after_seconds or 300.0), 30.0)
    max_attempts = max(int(max_attempts or 1), 1)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT id, update_key, bot_kind, update_json, attempts
                FROM telegram_webhook_updates
                WHERE attempts < ?
                  AND (
                    status = 'pending'
                    OR (status = 'processing' AND locked_at IS NOT NULL AND locked_at < ?)
                  )
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (max_attempts, stale_before),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            attempts = int(row["attempts"] or 0) + 1
            conn.execute(
                """
                UPDATE telegram_webhook_updates
                SET status='processing', attempts=?, locked_at=?, updated_at=?, last_error=NULL
                WHERE id=?
                """,
                (attempts, now, now, int(row["id"])),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    try:
        update = json.loads(row["update_json"] or "{}")
    except json.JSONDecodeError:
        logger.exception("Telegram webhook 队列 JSON 损坏 id=%s key=%s", row["id"], row["update_key"])
        fail_update(int(row["id"]), "invalid update_json", max_attempts=max_attempts)
        return None
    if not isinstance(update, dict):
        update = {}
    return QueuedTelegramUpdate(
        id=int(row["id"]),
        bot_kind=str(row["bot_kind"] or ""),
        update_key=str(row["update_key"] or ""),
        update=update,
        attempts=attempts,
    )


def ack_update(update_id: int) -> None:
    _ensure_schema()
    with _connect() as conn:
        conn.execute("DELETE FROM telegram_webhook_updates WHERE id=?", (int(update_id),))


def fail_update(update_id: int, error: str, *, max_attempts: int = 8) -> None:
    _ensure_schema()
    err = (error or "").strip()
    if len(err) > 1000:
        err = err[:1000]
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT attempts FROM telegram_webhook_updates WHERE id=?",
            (int(update_id),),
        ).fetchone()
        if row is None:
            return
        attempts = int(row["attempts"] or 0)
        status = "dead" if attempts >= max(int(max_attempts or 1), 1) else "pending"
        conn.execute(
            """
            UPDATE telegram_webhook_updates
            SET status=?, locked_at=NULL, updated_at=?, last_error=?
            WHERE id=?
            """,
            (status, now, err, int(update_id)),
        )


def queue_stats() -> dict[str, int]:
    _ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM telegram_webhook_updates
            GROUP BY status
            """
        ).fetchall()
    return {str(r["status"]): int(r["n"] or 0) for r in rows}
