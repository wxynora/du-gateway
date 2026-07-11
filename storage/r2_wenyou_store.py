"""Wenyou persistence facade: SQLite primary with optional R2 backup."""

from __future__ import annotations

from typing import Any, Optional

from config import R2_BUCKET_NAME, WENYOU_R2_BACKUP_ENABLED
from storage import wenyou_sqlite_store
from storage.r2_client import _read_json, _s3_client, _write_json
from utils.log import get_logger

logger = get_logger(__name__)


def wenyou_active_session_key(user_id: int) -> str:
    return f"wenyou/active/{int(user_id)}/session.json"


def wenyou_last_archive_key(user_id: int) -> str:
    return f"wenyou/last_archive/{int(user_id)}.json"


def wenyou_candidates_key(user_id: int) -> str:
    return f"wenyou/candidates/{int(user_id)}.json"


def wenyou_card_key(user_id: int) -> str:
    return f"wenyou/cards/{int(user_id)}.json"


def wenyou_wallet_key(user_id: int) -> str:
    return f"wenyou/wallet/{int(user_id)}.json"


def get_wenyou_session(user_id: int) -> Optional[Any]:
    """Read the active session, using R2 only to backfill missing SQLite data."""
    try:
        if wenyou_sqlite_store.has_session_record(user_id):
            return wenyou_sqlite_store.get_session(user_id)
    except Exception as exc:
        logger.warning("get_wenyou_session sqlite failed user_id=%s error=%s", user_id, exc)
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, wenyou_active_session_key(user_id))
    if data is not None:
        try:
            wenyou_sqlite_store.save_session(user_id, data)
        except Exception as exc:
            logger.warning("get_wenyou_session sqlite backfill failed user_id=%s error=%s", user_id, exc)
    return data


def save_wenyou_session(user_id: int, data: Any) -> bool:
    """Save a session to SQLite and optionally back it up to R2."""
    sqlite_ok = False
    try:
        sqlite_ok = wenyou_sqlite_store.save_session(user_id, data)
    except Exception as exc:
        logger.error("save_wenyou_session sqlite failed user_id=%s error=%s", user_id, exc, exc_info=True)
    if sqlite_ok and not WENYOU_R2_BACKUP_ENABLED:
        return True
    client = _s3_client()
    if not client:
        if not sqlite_ok:
            logger.warning("R2 unavailable and sqlite write failed for save_wenyou_session user_id=%s", user_id)
        return sqlite_ok
    try:
        _write_json(client, wenyou_active_session_key(user_id), data)
        return True
    except Exception as exc:
        logger.error("save_wenyou_session failed user_id=%s error=%s", user_id, exc, exc_info=True)
        return sqlite_ok


def delete_wenyou_active_session(user_id: int) -> bool:
    """Clear the active session without allowing an old R2 copy to resurrect it."""
    sqlite_ok = False
    try:
        sqlite_ok = wenyou_sqlite_store.delete_active_session(user_id)
    except Exception as exc:
        logger.error("delete_wenyou_active_session sqlite failed user_id=%s error=%s", user_id, exc, exc_info=True)
    if sqlite_ok and not WENYOU_R2_BACKUP_ENABLED:
        return True
    client = _s3_client()
    if not client:
        return sqlite_ok
    key = wenyou_active_session_key(user_id)
    try:
        client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except Exception as exc:
        logger.warning("delete_wenyou_active_session failed key=%s error=%s", key, exc)
        return sqlite_ok


def save_wenyou_archive_copy(user_id: int, game_id: str, data: Any) -> bool:
    """Archive one game to SQLite and optionally back it up to R2."""
    sqlite_ok = False
    try:
        sqlite_ok = wenyou_sqlite_store.save_archive_copy(user_id, game_id, data)
    except Exception as exc:
        logger.error(
            "save_wenyou_archive_copy sqlite failed user_id=%s game_id=%s error=%s",
            user_id,
            game_id,
            exc,
            exc_info=True,
        )
    if sqlite_ok and not WENYOU_R2_BACKUP_ENABLED:
        return True
    client = _s3_client()
    if not client:
        return sqlite_ok
    safe_gid = _safe_game_id(game_id)
    key = f"wenyou/archive/{int(user_id)}/{safe_gid or 'unknown'}.json"
    try:
        _write_json(client, key, data)
        return True
    except Exception as exc:
        logger.error("save_wenyou_archive_copy failed key=%s error=%s", key, exc, exc_info=True)
        return sqlite_ok


def save_wenyou_last_archive(user_id: int, data: Any) -> bool:
    """Save the most recently completed game snapshot."""
    sqlite_ok = False
    try:
        sqlite_ok = wenyou_sqlite_store.save_last_archive(user_id, data)
    except Exception as exc:
        logger.error("save_wenyou_last_archive sqlite failed user_id=%s error=%s", user_id, exc, exc_info=True)
    if sqlite_ok and not WENYOU_R2_BACKUP_ENABLED:
        return True
    client = _s3_client()
    if not client:
        return sqlite_ok
    try:
        _write_json(client, wenyou_last_archive_key(user_id), data)
        return True
    except Exception as exc:
        logger.error("save_wenyou_last_archive failed user_id=%s error=%s", user_id, exc, exc_info=True)
        return sqlite_ok


def get_wenyou_last_archive(user_id: int) -> Optional[Any]:
    """Read the latest completed game snapshot."""
    try:
        data = wenyou_sqlite_store.get_last_archive(user_id)
        if data is not None:
            return data
    except Exception as exc:
        logger.warning("get_wenyou_last_archive sqlite failed user_id=%s error=%s", user_id, exc)
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, wenyou_last_archive_key(user_id))
    if data is not None:
        try:
            wenyou_sqlite_store.save_last_archive(user_id, data)
        except Exception as exc:
            logger.warning("get_wenyou_last_archive sqlite backfill failed user_id=%s error=%s", user_id, exc)
    return data


def get_wenyou_candidates(user_id: int) -> Optional[Any]:
    """Read the candidate instance pool."""
    try:
        data = wenyou_sqlite_store.get_candidates(user_id)
        if data is not None:
            return data
    except Exception as exc:
        logger.warning("get_wenyou_candidates sqlite failed user_id=%s error=%s", user_id, exc)
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, wenyou_candidates_key(user_id))
    if data is not None:
        try:
            wenyou_sqlite_store.save_candidates(user_id, data)
        except Exception as exc:
            logger.warning("get_wenyou_candidates sqlite backfill failed user_id=%s error=%s", user_id, exc)
    return data


def save_wenyou_candidates(user_id: int, data: Any) -> bool:
    """Save the candidate instance pool."""
    return _save_kv_with_optional_backup(
        user_id=user_id,
        data=data,
        sqlite_saver=wenyou_sqlite_store.save_candidates,
        r2_key=wenyou_candidates_key(user_id),
        operation="save_wenyou_candidates",
    )


def get_wenyou_card(user_id: int) -> Optional[Any]:
    """Read the Wenyou continuity card."""
    return _get_kv_with_backfill(
        user_id=user_id,
        sqlite_getter=wenyou_sqlite_store.get_card,
        sqlite_saver=wenyou_sqlite_store.save_card,
        r2_key=wenyou_card_key(user_id),
        operation="get_wenyou_card",
    )


def save_wenyou_card(user_id: int, data: Any) -> bool:
    """Save the Wenyou continuity card."""
    return _save_kv_with_optional_backup(
        user_id=user_id,
        data=data,
        sqlite_saver=wenyou_sqlite_store.save_card,
        r2_key=wenyou_card_key(user_id),
        operation="save_wenyou_card",
    )


def get_wenyou_wallet(user_id: int) -> Optional[Any]:
    """Read the long-lived Wenyou wallet."""
    return _get_kv_with_backfill(
        user_id=user_id,
        sqlite_getter=wenyou_sqlite_store.get_wallet,
        sqlite_saver=wenyou_sqlite_store.save_wallet,
        r2_key=wenyou_wallet_key(user_id),
        operation="get_wenyou_wallet",
    )


def save_wenyou_wallet(user_id: int, data: Any) -> bool:
    """Save the long-lived Wenyou wallet."""
    return _save_kv_with_optional_backup(
        user_id=user_id,
        data=data,
        sqlite_saver=wenyou_sqlite_store.save_wallet,
        r2_key=wenyou_wallet_key(user_id),
        operation="save_wenyou_wallet",
    )


def list_wenyou_archives(user_id: int, limit: int = 20) -> list[dict]:
    """List completed games in reverse completion order."""
    try:
        sqlite_items = wenyou_sqlite_store.list_archives(user_id, limit=limit)
        if sqlite_items:
            return sqlite_items
    except Exception as exc:
        logger.warning("list_wenyou_archives sqlite failed user_id=%s error=%s", user_id, exc)
    client = _s3_client()
    if not client:
        return []
    lim = max(1, min(100, int(limit or 20)))
    prefix = f"wenyou/archive/{int(user_id)}/"
    objects: list[dict] = []
    token = None
    try:
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for obj in response.get("Contents") or []:
                key = str(obj.get("Key") or "")
                if key.endswith(".json"):
                    objects.append({"key": key, "last_modified": obj.get("LastModified")})
            if response.get("IsTruncated"):
                token = response.get("NextContinuationToken")
            else:
                break
    except Exception as exc:
        logger.warning("list_wenyou_archives key listing failed user_id=%s error=%s", user_id, exc)
        return []

    objects.sort(key=lambda item: str(item.get("last_modified") or ""), reverse=True)
    output: list[dict] = []
    for row in objects[: max(lim * 3, lim)]:
        key = row.get("key") or ""
        if not key:
            continue
        data = _read_json(client, key)
        if not isinstance(data, dict):
            continue
        try:
            wenyou_sqlite_store.save_archive_copy(user_id, str(data.get("gameId") or ""), data)
        except Exception as exc:
            logger.warning("list_wenyou_archives sqlite backfill failed key=%s error=%s", key, exc)
        output.append(_archive_summary(key, data))
        if len(output) >= lim:
            break
    output.sort(key=lambda item: str(item.get("endedAt") or ""), reverse=True)
    return output[:lim]


def get_wenyou_archive_by_game_id(user_id: int, game_id: str) -> Optional[Any]:
    """Read one completed game by game id."""
    try:
        data = wenyou_sqlite_store.get_archive_by_game_id(user_id, game_id)
        if data is not None:
            return data
    except Exception as exc:
        logger.warning(
            "get_wenyou_archive_by_game_id sqlite failed user_id=%s game_id=%s error=%s",
            user_id,
            game_id,
            exc,
        )
    client = _s3_client()
    if not client:
        return None
    safe_gid = _safe_game_id(game_id)
    if not safe_gid:
        return None
    key = f"wenyou/archive/{int(user_id)}/{safe_gid}.json"
    data = _read_json(client, key)
    if data is not None:
        try:
            wenyou_sqlite_store.save_archive_copy(user_id, safe_gid, data)
        except Exception as exc:
            logger.warning("get_wenyou_archive_by_game_id sqlite backfill failed key=%s error=%s", key, exc)
    return data


def _safe_game_id(game_id: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in (game_id or ""))[:80]


def _get_kv_with_backfill(*, user_id: int, sqlite_getter, sqlite_saver, r2_key: str, operation: str) -> Optional[Any]:
    try:
        data = sqlite_getter(user_id)
        if data is not None:
            return data
    except Exception as exc:
        logger.warning("%s sqlite failed user_id=%s error=%s", operation, user_id, exc)
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, r2_key)
    if data is not None:
        try:
            sqlite_saver(user_id, data)
        except Exception as exc:
            logger.warning("%s sqlite backfill failed user_id=%s error=%s", operation, user_id, exc)
    return data


def _save_kv_with_optional_backup(*, user_id: int, data: Any, sqlite_saver, r2_key: str, operation: str) -> bool:
    sqlite_ok = False
    try:
        sqlite_ok = sqlite_saver(user_id, data)
    except Exception as exc:
        logger.error("%s sqlite failed user_id=%s error=%s", operation, user_id, exc, exc_info=True)
    if sqlite_ok and not WENYOU_R2_BACKUP_ENABLED:
        return True
    client = _s3_client()
    if not client:
        if not sqlite_ok:
            logger.warning("R2 unavailable and sqlite write failed for %s user_id=%s", operation, user_id)
        return sqlite_ok
    try:
        _write_json(client, r2_key, data)
        return True
    except Exception as exc:
        logger.error("%s failed user_id=%s error=%s", operation, user_id, exc, exc_info=True)
        return sqlite_ok


def _archive_summary(key: str, data: dict) -> dict:
    framework = data.get("framework") if isinstance(data.get("framework"), dict) else {}
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    player1 = stats.get("player1") if isinstance(stats.get("player1"), dict) else {}
    player2 = stats.get("player2") if isinstance(stats.get("player2"), dict) else {}
    return {
        "key": key,
        "gameId": str(data.get("gameId") or ""),
        "endedAt": str(data.get("endedAt") or ""),
        "instance_code": str(framework.get("instance_code") or ""),
        "instance_name": str(framework.get("instance_name") or ""),
        "instance_genre": str(framework.get("instance_genre") or ""),
        "difficulty": str(framework.get("difficulty") or ""),
        "points": int(stats.get("points") or 0),
        "player1_name": str(framework.get("player1_name") or "玩家一"),
        "player2_name": str(framework.get("player2_name") or "渡"),
        "player1_level": int(player1.get("level") or 1),
        "player2_level": int(player2.get("level") or 1),
        "history_count": len(data.get("history") or []) if isinstance(data.get("history"), list) else 0,
    }
