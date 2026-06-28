"""Local SQLite runtime state for hot-path gateway data."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config import RUNTIME_STATE_DB

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False

_RUNTIME_TABLES = (
    "app_actions",
    "app_action_idempotency",
    "sense_latest",
    "sense_history",
    "device_reporting_config",
    "conversation_windows",
    "conversation_rounds",
    "schedule_items",
    "schedule_fired_keys",
    "conversation_followups",
    "spring_dream_sessions",
    "spring_dream_archives",
    "exchange_diary_entries",
)


def db_path() -> Path:
    return Path(RUNTIME_STATE_DB)


def _connect_raw() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with _connect_raw() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_actions (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    device_id TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'tool',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    leased_until TEXT NOT NULL DEFAULT '',
                    leased_at TEXT NOT NULL DEFAULT '',
                    leased_by_device_id TEXT NOT NULL DEFAULT '',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    finished_at TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_app_actions_status_created
                    ON app_actions(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_app_actions_pending_expires
                    ON app_actions(status, expires_at);
                CREATE INDEX IF NOT EXISTS idx_app_actions_history_finished
                    ON app_actions(status, finished_at);

                CREATE TABLE IF NOT EXISTS app_action_idempotency (
                    idem_key TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_app_action_idem_expires
                    ON app_action_idempotency(expires_at);

                CREATE TABLE IF NOT EXISTS sense_latest (
                    sense_type TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sense_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sense_type TEXT NOT NULL,
                    at TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sense_history_day
                    ON sense_history(at);
                CREATE INDEX IF NOT EXISTS idx_sense_history_type_at
                    ON sense_history(sense_type, at);
                CREATE INDEX IF NOT EXISTS idx_sense_history_expires
                    ON sense_history(expires_at);

                CREATE TABLE IF NOT EXISTS device_reporting_config (
                    device_id TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_windows (
                    window_id TEXT PRIMARY KEY,
                    last_round_index INTEGER NOT NULL DEFAULT 0,
                    next_round_index INTEGER NOT NULL DEFAULT 1,
                    round_count INTEGER NOT NULL DEFAULT 0,
                    recent_keep INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    bootstrapped_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS conversation_rounds (
                    window_id TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT '',
                    messages_json TEXT NOT NULL DEFAULT '[]',
                    action_note TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (window_id, round_index)
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_rounds_window_desc
                    ON conversation_rounds(window_id, round_index DESC);
                CREATE INDEX IF NOT EXISTS idx_conversation_rounds_window_timestamp
                    ON conversation_rounds(window_id, timestamp);

                CREATE TABLE IF NOT EXISTS schedule_items (
                    id TEXT PRIMARY KEY,
                    datetime TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    repeat TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    target_role TEXT NOT NULL DEFAULT '',
                    item_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_schedule_items_datetime
                    ON schedule_items(datetime, id);
                CREATE INDEX IF NOT EXISTS idx_schedule_items_enabled_datetime
                    ON schedule_items(enabled, datetime);

                CREATE TABLE IF NOT EXISTS schedule_fired_keys (
                    occurrence_key TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS conversation_followups (
                    id TEXT PRIMARY KEY,
                    position INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT '',
                    trigger_at TEXT NOT NULL DEFAULT '',
                    context_window_id TEXT NOT NULL DEFAULT '',
                    reply_channel TEXT NOT NULL DEFAULT '',
                    reply_target TEXT NOT NULL DEFAULT '',
                    thread_key TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    item_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_followups_position
                    ON conversation_followups(position);
                CREATE INDEX IF NOT EXISTS idx_conversation_followups_status_trigger
                    ON conversation_followups(status, trigger_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_followups_thread
                    ON conversation_followups(thread_key);

                CREATE TABLE IF NOT EXISTS spring_dream_sessions (
                    sleep_session_key TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    max_per_sleep INTEGER NOT NULL DEFAULT 3,
                    last_theme_id TEXT NOT NULL DEFAULT '',
                    sleep_source TEXT NOT NULL DEFAULT '',
                    reserved_at TEXT NOT NULL DEFAULT '',
                    last_sent_at TEXT NOT NULL DEFAULT '',
                    post_wakeup_pending INTEGER NOT NULL DEFAULT 0,
                    post_wakeup_sent_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_sessions_updated
                    ON spring_dream_sessions(updated_at);

                CREATE TABLE IF NOT EXISTS spring_dream_archives (
                    id TEXT PRIMARY KEY,
                    window_id TEXT NOT NULL DEFAULT '',
                    sleep_session_key TEXT NOT NULL DEFAULT '',
                    theme_id TEXT NOT NULL DEFAULT '',
                    sleep_source TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    sent_at TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL DEFAULT '',
                    fragments_json TEXT NOT NULL DEFAULT '[]',
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    r2_key TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_archives_sent
                    ON spring_dream_archives(sent_at DESC);
                CREATE INDEX IF NOT EXISTS idx_spring_dream_archives_session
                    ON spring_dream_archives(sleep_session_key, sent_at DESC);
                CREATE INDEX IF NOT EXISTS idx_spring_dream_archives_window
                    ON spring_dream_archives(window_id, sent_at DESC);

                CREATE TABLE IF NOT EXISTS exchange_diary_entries (
                    id TEXT PRIMARY KEY,
                    entry_key TEXT NOT NULL,
                    diary_date TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    excerpt TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    mood TEXT NOT NULL DEFAULT '',
                    comment_count INTEGER NOT NULL DEFAULT 0,
                    latest_comment_at TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    client_request_id TEXT NOT NULL DEFAULT '',
                    created_by_device_id TEXT NOT NULL DEFAULT '',
                    source_window_id TEXT NOT NULL DEFAULT '',
                    source_notion_page_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    deleted_at TEXT NOT NULL DEFAULT '',
                    entry_json TEXT NOT NULL DEFAULT '{}',
                    r2_synced_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_exchange_diary_visible_date
                    ON exchange_diary_entries(deleted_at, diary_date DESC, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_exchange_diary_author_date
                    ON exchange_diary_entries(author, diary_date DESC, created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_exchange_diary_client_request
                    ON exchange_diary_entries(client_request_id)
                    WHERE client_request_id != '';
                CREATE UNIQUE INDEX IF NOT EXISTS idx_exchange_diary_notion_page
                    ON exchange_diary_entries(source_notion_page_id)
                    WHERE source_notion_page_id != '';
                """
            )
        _SCHEMA_READY = True


def connect() -> sqlite3.Connection:
    ensure_schema()
    return _connect_raw()


def clear_all_tables() -> int:
    """Clear runtime SQLite mirrors without deleting the database file."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for table in _RUNTIME_TABLES:
                conn.execute(f"DELETE FROM {table}")
            conn.execute("COMMIT")
            return len(_RUNTIME_TABLES)
        except Exception:
            conn.execute("ROLLBACK")
            raise


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def json_loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(str(raw or ""))
    except Exception:
        return fallback
