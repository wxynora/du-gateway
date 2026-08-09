import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from config import TELEGRAM_WEBHOOK_QUEUE_DB
from runtime.events import EventEnvelope, TELEGRAM_WEBHOOK_JOB_CREATED
from runtime.outbox import ensure_outbox_schema, insert_outbox_event, notify_outbox_dispatcher
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
    lease_token: str = ""


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
                    lease_token TEXT,
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
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(telegram_webhook_updates)").fetchall()
            }
            if "lease_token" not in columns:
                conn.execute("ALTER TABLE telegram_webhook_updates ADD COLUMN lease_token TEXT")
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


def telegram_update_partition_key(update: dict, bot_kind: str) -> str:
    clean_update = update if isinstance(update, dict) else {}
    message = (
        clean_update.get("message")
        or clean_update.get("edited_message")
        or clean_update.get("channel_post")
        or clean_update.get("edited_channel_post")
        or {}
    )
    callback = clean_update.get("callback_query") or {}
    callback_message = callback.get("message") if isinstance(callback, dict) else {}
    chat = (
        message.get("chat") if isinstance(message, dict) else {}
    ) or (
        callback_message.get("chat") if isinstance(callback_message, dict) else {}
    ) or {}
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    if chat_id is None and isinstance(callback, dict):
        from_user = callback.get("from") or {}
        chat_id = from_user.get("id") if isinstance(from_user, dict) else None
    return f"telegram:{bot_kind}:chat:{chat_id}" if chat_id is not None else f"telegram:{bot_kind}:global"


def enqueue_update(update: dict, bot_kind: str) -> EnqueueResult:
    _ensure_schema()
    kind = _normalize_bot_kind(bot_kind)
    clean_update = update if isinstance(update, dict) else {}
    update_key = make_update_key(clean_update, kind)
    now = time.time()
    payload = json.dumps(clean_update, ensure_ascii=False, separators=(",", ":"))
    event = EventEnvelope.create(
        TELEGRAM_WEBHOOK_JOB_CREATED,
        job_id=update_key,
        partition_key=telegram_update_partition_key(clean_update, kind),
        payload={"bot_kind": kind, "update_key": update_key},
    )
    result: EnqueueResult
    with _connect() as conn:
        ensure_outbox_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            inserted = True
            try:
                conn.execute(
                    """
                    INSERT INTO telegram_webhook_updates
                        (update_key, bot_kind, update_json, status, attempts, locked_at,
                         lease_token, created_at, updated_at, last_error)
                    VALUES (?, ?, ?, 'pending', 0, NULL, NULL, ?, ?, NULL)
                    """,
                    (update_key, kind, payload, now, now),
                )
            except sqlite3.IntegrityError:
                inserted = False
            if inserted:
                insert_outbox_event(conn, event, aggregate_type="telegram_webhook_update")
            conn.execute("COMMIT")
            result = EnqueueResult(
                enqueued=inserted,
                duplicate=not inserted,
                update_key=update_key,
            )
        except Exception:
            conn.execute("ROLLBACK")
            raise
    if result.enqueued:
        notify_outbox_dispatcher("telegram")
    return result


def claim_next_update(
    *,
    stale_after_seconds: float = 300.0,
    max_attempts: int = 8,
) -> QueuedTelegramUpdate | None:
    _ensure_schema()
    now = time.time()
    stale_before = now - max(float(stale_after_seconds or 300.0), 30.0)
    max_attempts = max(int(max_attempts or 1), 1)
    lease_token = uuid4().hex
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
                SET status='processing', attempts=?, locked_at=?, lease_token=?,
                    updated_at=?, last_error=NULL
                WHERE id=?
                """,
                (attempts, now, lease_token, now, int(row["id"])),
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
        lease_token=lease_token,
    )


def claim_update_by_key(
    update_key: str,
    *,
    stale_after_seconds: float = 300.0,
    max_attempts: int = 8,
) -> QueuedTelegramUpdate | None:
    _ensure_schema()
    key = str(update_key or "").strip()
    if not key:
        return None
    now = time.time()
    stale_before = now - max(float(stale_after_seconds or 300.0), 30.0)
    max_attempts = max(int(max_attempts or 1), 1)
    lease_token = uuid4().hex
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT id, update_key, bot_kind, update_json, attempts
                FROM telegram_webhook_updates
                WHERE update_key=?
                  AND attempts < ?
                  AND (
                    status='pending'
                    OR (
                        status='processing'
                        AND (locked_at IS NULL OR locked_at<?)
                    )
                  )
                LIMIT 1
                """,
                (key, max_attempts, stale_before),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            attempts = int(row["attempts"] or 0) + 1
            conn.execute(
                """
                UPDATE telegram_webhook_updates
                SET status='processing', attempts=?, locked_at=?, lease_token=?,
                    updated_at=?, last_error=NULL
                WHERE id=?
                """,
                (attempts, now, lease_token, now, int(row["id"])),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    try:
        update = json.loads(row["update_json"] or "{}")
    except json.JSONDecodeError:
        logger.exception("Telegram webhook 队列 JSON 损坏 id=%s key=%s", row["id"], row["update_key"])
        fail_update(
            int(row["id"]),
            "invalid update_json",
            max_attempts=max_attempts,
            lease_token=lease_token,
        )
        return None
    if not isinstance(update, dict):
        update = {}
    return QueuedTelegramUpdate(
        id=int(row["id"]),
        bot_kind=str(row["bot_kind"] or ""),
        update_key=str(row["update_key"] or ""),
        update=update,
        attempts=attempts,
        lease_token=lease_token,
    )


def ack_update(update_id: int, *, lease_token: str = "") -> bool:
    _ensure_schema()
    lease = str(lease_token or "").strip()
    with _connect() as conn:
        if lease:
            cur = conn.execute(
                "DELETE FROM telegram_webhook_updates WHERE id=? AND lease_token=?",
                (int(update_id), lease),
            )
        else:
            cur = conn.execute(
                "DELETE FROM telegram_webhook_updates WHERE id=?",
                (int(update_id),),
            )
    return int(cur.rowcount or 0) > 0


def fail_update(
    update_id: int,
    error: str,
    *,
    max_attempts: int = 8,
    lease_token: str = "",
) -> bool:
    _ensure_schema()
    err = (error or "").strip()
    if len(err) > 1000:
        err = err[:1000]
    now = time.time()
    lease = str(lease_token or "").strip()
    with _connect() as conn:
        if lease:
            row = conn.execute(
                "SELECT attempts FROM telegram_webhook_updates WHERE id=? AND lease_token=?",
                (int(update_id), lease),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT attempts FROM telegram_webhook_updates WHERE id=?",
                (int(update_id),),
            ).fetchone()
        if row is None:
            return False
        attempts = int(row["attempts"] or 0)
        status = "dead" if attempts >= max(int(max_attempts or 1), 1) else "pending"
        where = "id=?"
        params: list = [status, now, err, int(update_id)]
        if lease:
            where += " AND lease_token=?"
            params.append(lease)
        cur = conn.execute(
            f"""
            UPDATE telegram_webhook_updates
            SET status=?, locked_at=NULL, lease_token=NULL, updated_at=?, last_error=?
            WHERE {where}
            """,
            params,
        )
    return int(cur.rowcount or 0) > 0


def dead_letter_update(update_key: str, error: str) -> bool:
    _ensure_schema()
    err = str(error or "").replace("\r", " ").replace("\n", " ").strip()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE telegram_webhook_updates
            SET status='dead', locked_at=NULL, lease_token=NULL,
                updated_at=?, last_error=?
            WHERE update_key=? AND status!='dead'
            """,
            (time.time(), err, str(update_key or "")),
        )
    return int(cur.rowcount or 0) > 0


def get_update_status(update_key: str) -> tuple[str, int] | None:
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            "SELECT status, attempts FROM telegram_webhook_updates WHERE update_key=? LIMIT 1",
            (str(update_key or ""),),
        ).fetchone()
    if row is None:
        return None
    return str(row["status"] or ""), int(row["attempts"] or 0)


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
