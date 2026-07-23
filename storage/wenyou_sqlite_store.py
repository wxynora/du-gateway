"""SQLite primary store for Wenyou game state."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from config import WENYOU_SQLITE_DB
from utils.time_aware import now_beijing_iso

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def db_path() -> Path:
    return Path(WENYOU_SQLITE_DB)


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
                CREATE TABLE IF NOT EXISTS wenyou_kv (
                    user_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT 'null',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (user_id, kind)
                );
                CREATE INDEX IF NOT EXISTS idx_wenyou_kv_kind_updated
                    ON wenyou_kv(kind, updated_at);

                CREATE TABLE IF NOT EXISTS wenyou_archives (
                    user_id INTEGER NOT NULL,
                    game_id TEXT NOT NULL,
                    ended_at TEXT NOT NULL DEFAULT '',
                    instance_code TEXT NOT NULL DEFAULT '',
                    instance_name TEXT NOT NULL DEFAULT '',
                    instance_genre TEXT NOT NULL DEFAULT '',
                    difficulty TEXT NOT NULL DEFAULT '',
                    points INTEGER NOT NULL DEFAULT 0,
                    player1_name TEXT NOT NULL DEFAULT '玩家一',
                    player2_name TEXT NOT NULL DEFAULT '玩家二',
                    player1_level INTEGER NOT NULL DEFAULT 1,
                    player2_level INTEGER NOT NULL DEFAULT 1,
                    history_count INTEGER NOT NULL DEFAULT 0,
                    archive_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (user_id, game_id)
                );
                CREATE INDEX IF NOT EXISTS idx_wenyou_archives_user_ended
                    ON wenyou_archives(user_id, ended_at DESC);
                CREATE INDEX IF NOT EXISTS idx_wenyou_archives_user_updated
                    ON wenyou_archives(user_id, updated_at DESC);
                """
            )
        _SCHEMA_READY = True


def connect() -> sqlite3.Connection:
    ensure_schema()
    return _connect_raw()


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def json_loads(raw: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(str(raw or ""))
    except Exception:
        return fallback


def _safe_game_id(game_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (game_id or ""))[:80]


def _archive_summary(data: Any) -> dict:
    archive = data if isinstance(data, dict) else {}
    fw = archive.get("framework") if isinstance(archive.get("framework"), dict) else {}
    st = archive.get("stats") if isinstance(archive.get("stats"), dict) else {}
    p1 = st.get("player1") if isinstance(st.get("player1"), dict) else {}
    p2 = st.get("player2") if isinstance(st.get("player2"), dict) else {}
    return {
        "ended_at": str(archive.get("endedAt") or ""),
        "instance_code": str(fw.get("instance_code") or ""),
        "instance_name": str(fw.get("instance_name") or ""),
        "instance_genre": str(fw.get("instance_genre") or ""),
        "difficulty": str(fw.get("difficulty") or ""),
        "points": int(st.get("points") or 0),
        "player1_name": str(fw.get("player1_name") or "玩家一"),
        "player2_name": str(fw.get("player2_name") or "玩家二"),
        "player1_level": int(p1.get("level") or 1),
        "player2_level": int(p2.get("level") or 1),
        "history_count": len(archive.get("history") or []) if isinstance(archive.get("history"), list) else 0,
    }


def has_kv(user_id: int, kind: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM wenyou_kv WHERE user_id = ? AND kind = ?",
            (int(user_id), str(kind)),
        ).fetchone()
    return row is not None


def get_kv(user_id: int, kind: str) -> Optional[Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT data_json FROM wenyou_kv WHERE user_id = ? AND kind = ?",
            (int(user_id), str(kind)),
        ).fetchone()
    if row is None:
        return None
    return json_loads(row["data_json"], None)


def save_kv(user_id: int, kind: str, data: Any) -> bool:
    now = now_beijing_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO wenyou_kv (user_id, kind, data_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, kind) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (int(user_id), str(kind), json_dumps(data), now),
        )
    return True


def get_session(user_id: int) -> Optional[Any]:
    return get_kv(user_id, "session")


def has_session_record(user_id: int) -> bool:
    return has_kv(user_id, "session")


def save_session(user_id: int, data: Any) -> bool:
    return save_kv(user_id, "session", data)


def delete_active_session(user_id: int) -> bool:
    return save_kv(user_id, "session", None)


def get_last_archive(user_id: int) -> Optional[Any]:
    return get_kv(user_id, "last_archive")


def save_last_archive(user_id: int, data: Any) -> bool:
    return save_kv(user_id, "last_archive", data)


def get_candidates(user_id: int) -> Optional[Any]:
    return get_kv(user_id, "candidates")


def save_candidates(user_id: int, data: Any) -> bool:
    return save_kv(user_id, "candidates", data)


def get_card(user_id: int) -> Optional[Any]:
    return get_kv(user_id, "card")


def save_card(user_id: int, data: Any) -> bool:
    return save_kv(user_id, "card", data)


def get_wallet(user_id: int) -> Optional[Any]:
    return get_kv(user_id, "wallet")


def save_wallet(user_id: int, data: Any) -> bool:
    return save_kv(user_id, "wallet", data)


def save_archive_copy(user_id: int, game_id: str, data: Any) -> bool:
    safe_gid = _safe_game_id(game_id) or "unknown"
    summary = _archive_summary(data)
    now = now_beijing_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO wenyou_archives (
                user_id, game_id, ended_at, instance_code, instance_name, instance_genre,
                difficulty, points, player1_name, player2_name, player1_level,
                player2_level, history_count, archive_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, game_id) DO UPDATE SET
                ended_at = excluded.ended_at,
                instance_code = excluded.instance_code,
                instance_name = excluded.instance_name,
                instance_genre = excluded.instance_genre,
                difficulty = excluded.difficulty,
                points = excluded.points,
                player1_name = excluded.player1_name,
                player2_name = excluded.player2_name,
                player1_level = excluded.player1_level,
                player2_level = excluded.player2_level,
                history_count = excluded.history_count,
                archive_json = excluded.archive_json,
                updated_at = excluded.updated_at
            """,
            (
                int(user_id),
                safe_gid,
                summary["ended_at"],
                summary["instance_code"],
                summary["instance_name"],
                summary["instance_genre"],
                summary["difficulty"],
                summary["points"],
                summary["player1_name"],
                summary["player2_name"],
                summary["player1_level"],
                summary["player2_level"],
                summary["history_count"],
                json_dumps(data),
                now,
            ),
        )
    return True


def list_archives(user_id: int, limit: int = 20) -> list[dict]:
    lim = max(1, min(100, int(limit or 20)))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT game_id, ended_at, instance_code, instance_name, instance_genre,
                   difficulty, points, player1_name, player2_name, player1_level,
                   player2_level, history_count
            FROM wenyou_archives
            WHERE user_id = ?
            ORDER BY ended_at DESC, rowid DESC
            LIMIT ?
            """,
            (int(user_id), lim),
        ).fetchall()
    return [
        {
            "key": f"sqlite:wenyou/archive/{int(user_id)}/{row['game_id']}.json",
            "gameId": str(row["game_id"] or ""),
            "endedAt": str(row["ended_at"] or ""),
            "instance_code": str(row["instance_code"] or ""),
            "instance_name": str(row["instance_name"] or ""),
            "instance_genre": str(row["instance_genre"] or ""),
            "difficulty": str(row["difficulty"] or ""),
            "points": int(row["points"] or 0),
            "player1_name": str(row["player1_name"] or "玩家一"),
            "player2_name": str(row["player2_name"] or "玩家二"),
            "player1_level": int(row["player1_level"] or 1),
            "player2_level": int(row["player2_level"] or 1),
            "history_count": int(row["history_count"] or 0),
        }
        for row in rows
    ]


def get_archive_by_game_id(user_id: int, game_id: str) -> Optional[Any]:
    safe_gid = _safe_game_id(game_id)
    if not safe_gid:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT archive_json FROM wenyou_archives WHERE user_id = ? AND game_id = ?",
            (int(user_id), safe_gid),
        ).fetchone()
    if row is None:
        return None
    return json_loads(row["archive_json"], None)


def clear_all_tables() -> int:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM wenyou_kv")
            conn.execute("DELETE FROM wenyou_archives")
            conn.execute("COMMIT")
            return 2
        except Exception:
            conn.execute("ROLLBACK")
            raise
