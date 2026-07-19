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
    "spring_dream_trigger_state",
    "spring_dream_archives",
    "spring_dream_inspiration",
    "spring_dream_theme_draws",
    "spring_dream_consumptions",
    "exchange_diary_entries",
    "recall_message_markers",
    "recall_message_targets",
    "tool_result_cache",
    "du_body_eval_pending",
    "du_body_eval_audit",
    "watch_sessions",
    "watch_timeline_sections",
    "watch_plot_chunks",
    "watch_risk_events",
    "watch_risk_feedback",
    "watch_analysis_samples",
    "watch_analysis_jobs",
    "watch_timeline_fingerprints",
    "watch_story_checkpoints",
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

                CREATE TABLE IF NOT EXISTS recall_message_markers (
                    id TEXT PRIMARY KEY,
                    window_id TEXT NOT NULL DEFAULT '',
                    message_id TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recall_message_markers_window_created
                    ON recall_message_markers(window_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_recall_message_markers_message
                    ON recall_message_markers(message_id);

                CREATE TABLE IF NOT EXISTS recall_message_targets (
                    candidate_set_id TEXT PRIMARY KEY,
                    window_id TEXT NOT NULL DEFAULT '',
                    client_request_id TEXT NOT NULL DEFAULT '',
                    targets_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recall_message_targets_window_created
                    ON recall_message_targets(window_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_recall_message_targets_client
                    ON recall_message_targets(window_id, client_request_id);
                CREATE INDEX IF NOT EXISTS idx_recall_message_targets_expires
                    ON recall_message_targets(expires_at);

                CREATE TABLE IF NOT EXISTS tool_result_cache (
                    id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    window_id TEXT NOT NULL DEFAULT '',
                    reply_channel TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_result_cache_created
                    ON tool_result_cache(created_at, id);
                CREATE INDEX IF NOT EXISTS idx_tool_result_cache_expires
                    ON tool_result_cache(expires_at);

                CREATE TABLE IF NOT EXISTS du_body_eval_pending (
                    window_id TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    round_hash TEXT NOT NULL,
                    round_timestamp TEXT NOT NULL DEFAULT '',
                    messages_json TEXT NOT NULL DEFAULT '[]',
                    prompt_version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    batch_id TEXT NOT NULL DEFAULT '',
                    lease_until REAL NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    queued_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (window_id, round_index)
                );
                CREATE INDEX IF NOT EXISTS idx_du_body_eval_pending_due
                    ON du_body_eval_pending(window_id, status, next_attempt_at, round_index);
                CREATE INDEX IF NOT EXISTS idx_du_body_eval_pending_lease
                    ON du_body_eval_pending(status, lease_until);

                CREATE TABLE IF NOT EXISTS du_body_eval_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    window_id TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    round_hash TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    batch_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    event_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_du_body_eval_audit_window_round
                    ON du_body_eval_audit(window_id, round_index, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_du_body_eval_audit_created
                    ON du_body_eval_audit(created_at DESC);

                CREATE TABLE IF NOT EXISTS watch_sessions (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL DEFAULT '',
                    window_id TEXT NOT NULL DEFAULT '',
                    companion_id TEXT NOT NULL DEFAULT '',
                    companion_name TEXT NOT NULL DEFAULT '',
                    media_id TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    part_title TEXT NOT NULL DEFAULT '',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    knowledge_mode TEXT NOT NULL DEFAULT 'known',
                    analysis_familiarity TEXT NOT NULL DEFAULT 'pending',
                    analysis_identity TEXT NOT NULL DEFAULT '',
                    analysis_model TEXT NOT NULL DEFAULT 'google/gemini-2.5-flash',
                    analysis_prompt_version TEXT NOT NULL DEFAULT 'watch-v2',
                    force_unknown_analysis INTEGER NOT NULL DEFAULT 0,
                    fear_mode INTEGER NOT NULL DEFAULT 0,
                    fear_action TEXT NOT NULL DEFAULT 'warn_only',
                    reduce_volume INTEGER NOT NULL DEFAULT 0,
                    danmaku_enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'paused',
                    playhead_ms INTEGER NOT NULL DEFAULT 0,
                    is_playing INTEGER NOT NULL DEFAULT 0,
                    playback_rate REAL NOT NULL DEFAULT 1.0,
                    timeline_epoch INTEGER NOT NULL DEFAULT 0,
                    snapshot_seq INTEGER NOT NULL DEFAULT 0,
                    captured_at TEXT NOT NULL DEFAULT '',
                    analysis_status TEXT NOT NULL DEFAULT 'pending',
                    analysis_covered_from_ms INTEGER NOT NULL DEFAULT 0,
                    analysis_covered_until_ms INTEGER NOT NULL DEFAULT 0,
                    analysis_error TEXT NOT NULL DEFAULT '',
                    story_so_far_json TEXT NOT NULL DEFAULT '{}',
                    analysis_story_state_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_watch_sessions_device_updated
                    ON watch_sessions(device_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_watch_sessions_window_updated
                    ON watch_sessions(window_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_watch_sessions_expires
                    ON watch_sessions(expires_at);

                CREATE TABLE IF NOT EXISTS watch_timeline_sections (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timeline_epoch INTEGER NOT NULL DEFAULT 0,
                    kind TEXT NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'analysis',
                    confidence REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_watch_timeline_session_range
                    ON watch_timeline_sections(session_id, timeline_epoch, start_ms, end_ms);

                CREATE TABLE IF NOT EXISTS watch_plot_chunks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    media_id TEXT NOT NULL DEFAULT '',
                    timeline_epoch INTEGER NOT NULL DEFAULT 0,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    visual_description TEXT NOT NULL DEFAULT '',
                    dialogue_summary TEXT NOT NULL DEFAULT '',
                    characters_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0,
                    analysis_version TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_watch_plot_session_range
                    ON watch_plot_chunks(session_id, timeline_epoch, start_ms, end_ms);

                CREATE TABLE IF NOT EXISTS watch_risk_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    media_id TEXT NOT NULL DEFAULT '',
                    timeline_epoch INTEGER NOT NULL DEFAULT 0,
                    risk_type TEXT NOT NULL DEFAULT 'high_energy',
                    severity TEXT NOT NULL DEFAULT 'medium',
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    warn_at_ms INTEGER NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    companion_hint TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    analysis_version TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_watch_risk_session_warn
                    ON watch_risk_events(session_id, timeline_epoch, warn_at_ms, end_ms);

                CREATE TABLE IF NOT EXISTS watch_risk_feedback (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    risk_event_id TEXT NOT NULL DEFAULT '',
                    feedback_type TEXT NOT NULL,
                    playhead_ms INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    device_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_watch_risk_feedback_session_created
                    ON watch_risk_feedback(session_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS watch_analysis_samples (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    media_id TEXT NOT NULL,
                    timeline_epoch INTEGER NOT NULL DEFAULT 0,
                    purpose TEXT NOT NULL DEFAULT 'rolling',
                    at_ms INTEGER NOT NULL DEFAULT 0,
                    mime_type TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL DEFAULT '',
                    text_content TEXT NOT NULL DEFAULT '',
                    subtitle TEXT NOT NULL DEFAULT '',
                    sha256 TEXT NOT NULL DEFAULT '',
                    perceptual_hash TEXT NOT NULL DEFAULT '',
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    byte_size INTEGER NOT NULL DEFAULT 0,
                    captured_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT NOT NULL DEFAULT '',
                    purged_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_watch_analysis_samples_session_range
                    ON watch_analysis_samples(session_id, timeline_epoch, purpose, at_ms);
                CREATE INDEX IF NOT EXISTS idx_watch_analysis_samples_expires
                    ON watch_analysis_samples(expires_at, purged_at);

                CREATE TABLE IF NOT EXISTS watch_analysis_jobs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL,
                    media_id TEXT NOT NULL,
                    timeline_epoch INTEGER NOT NULL DEFAULT 0,
                    purpose TEXT NOT NULL DEFAULT 'rolling',
                    input_origin TEXT NOT NULL DEFAULT 'client_upload',
                    planned_timestamps_json TEXT NOT NULL DEFAULT '[]',
                    range_start_ms INTEGER NOT NULL DEFAULT 0,
                    range_end_ms INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    available_at TEXT NOT NULL,
                    leased_until TEXT NOT NULL DEFAULT '',
                    lease_token TEXT NOT NULL DEFAULT '',
                    sample_ids_json TEXT NOT NULL DEFAULT '[]',
                    analysis_version TEXT NOT NULL DEFAULT '',
                    input_bytes INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    usage_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_watch_analysis_jobs_idempotency
                    ON watch_analysis_jobs(idempotency_key)
                    WHERE idempotency_key != '';
                CREATE INDEX IF NOT EXISTS idx_watch_analysis_jobs_claim
                    ON watch_analysis_jobs(status, available_at, priority DESC, created_at);
                CREATE INDEX IF NOT EXISTS idx_watch_analysis_jobs_session
                    ON watch_analysis_jobs(session_id, timeline_epoch, created_at DESC);

                CREATE TABLE IF NOT EXISTS watch_timeline_fingerprints (
                    id TEXT PRIMARY KEY,
                    series_key TEXT NOT NULL,
                    source_media_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    section_start_ms INTEGER NOT NULL,
                    section_end_ms INTEGER NOT NULL,
                    sample_at_ms INTEGER NOT NULL,
                    perceptual_hash TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_watch_timeline_fingerprints_series
                    ON watch_timeline_fingerprints(series_key, kind, sample_at_ms);

                CREATE TABLE IF NOT EXISTS watch_story_checkpoints (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    media_id TEXT NOT NULL,
                    timeline_epoch INTEGER NOT NULL DEFAULT 0,
                    through_ms INTEGER NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    story_state_json TEXT NOT NULL DEFAULT '{}',
                    analysis_version TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES watch_sessions(id) ON DELETE CASCADE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_watch_story_checkpoint_unique
                    ON watch_story_checkpoints(session_id, timeline_epoch, through_ms, analysis_version);
                CREATE INDEX IF NOT EXISTS idx_watch_story_checkpoint_lookup
                    ON watch_story_checkpoints(session_id, timeline_epoch, through_ms DESC);

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

                CREATE TABLE IF NOT EXISTS spring_dream_trigger_state (
                    id TEXT PRIMARY KEY,
                    miss_count INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT NOT NULL DEFAULT '',
                    last_triggered_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );

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

                CREATE TABLE IF NOT EXISTS spring_dream_inspiration (
                    id TEXT PRIMARY KEY,
                    stars_json TEXT NOT NULL DEFAULT '[]',
                    theme_id TEXT NOT NULL DEFAULT '',
                    consume_token TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS spring_dream_theme_draws (
                    draw_id TEXT PRIMARY KEY,
                    theme_id TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    selected_at TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_theme_draws_selected
                    ON spring_dream_theme_draws(selected_at DESC);

                CREATE TABLE IF NOT EXISTS spring_dream_consumptions (
                    consume_token TEXT PRIMARY KEY,
                    sleep_session_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    reserved_at TEXT NOT NULL DEFAULT '',
                    sent_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_consumptions_status
                    ON spring_dream_consumptions(status, updated_at DESC);

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
            job_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(watch_analysis_jobs)").fetchall()
            }
            if "input_origin" not in job_columns:
                conn.execute(
                    "ALTER TABLE watch_analysis_jobs "
                    "ADD COLUMN input_origin TEXT NOT NULL DEFAULT 'client_upload'"
                )
            if "planned_timestamps_json" not in job_columns:
                conn.execute(
                    "ALTER TABLE watch_analysis_jobs "
                    "ADD COLUMN planned_timestamps_json TEXT NOT NULL DEFAULT '[]'"
                )
            conn.execute("DROP TABLE IF EXISTS model_token_ratios")
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
