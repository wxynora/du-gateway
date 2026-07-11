"""Compact conversation archives with SQLite hot reads and R2 compatibility."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Optional

from botocore.exceptions import ClientError

from config import R2_BUCKET_NAME
from storage import conversation_sqlite_store
from storage.r2_client import _read_json, _s3_client, _write_json
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso, today_beijing

logger = get_logger(__name__)

WINDOW_ID_DEFAULT = "__default__"
LEGACY_EMPTY_CONVERSATION_KEY = "windows//conversation.json"
CONVERSATION_COMPACT_SCHEMA_VERSION = 2
CONVERSATION_RECENT_MAX_ROUNDS = 120
CONVERSATION_GUARD_BACKUP_DAYS = 3

_conversation_write_lock = threading.Lock()


def _get_key(prefix: str, key: str) -> str:
    return f"{prefix}/{key}" if prefix else key

def normalize_window_id(window_id: str) -> str:
    """空或仅空白视为默认窗口，保证轮次累计与总结触发与显式 id 一致。"""
    w = (window_id or "").strip()
    return w if w else WINDOW_ID_DEFAULT


def _prefix(window_id: str) -> str:
    return f"windows/{normalize_window_id(window_id)}"


def _conversation_meta_key(window_id: str) -> str:
    return _get_key(_prefix(window_id), "conversation_meta.json")


def _conversation_recent_key(window_id: str) -> str:
    return _get_key(_prefix(window_id), "recent_rounds.json")


def _conversation_round_key(window_id: str, round_index: int) -> str:
    return _get_key(_prefix(window_id), f"rounds/{int(round_index):06d}.json")


def _image_desc_recent_key(window_id: str) -> str:
    return _get_key(_prefix(window_id), "image_descriptions_recent.json")


def _pseudo_cot_state_key(window_id: str) -> str:
    return _get_key(_prefix(window_id), "pseudo_cot_state.json")


def _round_index_value(round_entry: dict) -> int:
    try:
        return int((round_entry or {}).get("index") or 0)
    except Exception:
        return 0


def _sort_rounds(rounds: list[dict]) -> list[dict]:
    return sorted(
        [r for r in (rounds or []) if isinstance(r, dict)],
        key=lambda r: (_round_index_value(r), str(r.get("timestamp") or "")),
    )


def _latest_rounds(rounds: list[dict], limit: int) -> list[dict]:
    try:
        n = int(limit or 0)
    except Exception:
        n = 0
    if n <= 0:
        return []
    return _sort_rounds(rounds)[-n:]


def _empty_conversation_meta(window_id: str) -> dict:
    return {
        "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
        "window_id": normalize_window_id(window_id),
        "last_round_index": 0,
        "next_round_index": 1,
        "round_count": 0,
        "recent_keep": CONVERSATION_RECENT_MAX_ROUNDS,
        "updated_at": now_beijing_iso(),
    }


def _merge_rounds_by_index(round_groups: list[list[dict]]) -> list[dict]:
    merged: dict[int, dict] = {}
    for rounds in round_groups:
        for r in rounds or []:
            if not isinstance(r, dict):
                continue
            idx = _round_index_value(r)
            if idx <= 0:
                continue
            prev = merged.get(idx)
            if prev is None or str(r.get("timestamp") or "") >= str(prev.get("timestamp") or ""):
                merged[idx] = r
    return _sort_rounds(list(merged.values()))


def _conversation_guard_dates(days: int = CONVERSATION_GUARD_BACKUP_DAYS) -> list[str]:
    today = datetime.now(BEIJING_TZ).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(max(1, int(days or 1)))]


def _read_conversation_backup_rounds_for_dates(client, window_id: str, dates: list[str]) -> list[dict]:
    out: list[dict] = []
    for date in dates or []:
        key = _conversations_key_for_date(window_id, str(date))
        data = _read_json(client, key)
        rounds = data.get("rounds") if isinstance(data, dict) else []
        if isinstance(rounds, list):
            out.extend(r for r in rounds if isinstance(r, dict))
    return _sort_rounds(out)


def _read_conversation_meta_status(client, window_id: str) -> tuple[dict, bool, bool]:
    key = _conversation_meta_key(window_id)
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        data = json.loads(resp["Body"].read().decode("utf-8"))
        return (data if isinstance(data, dict) else {}, True, False)
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return {}, True, True
        logger.error("R2 read conversation_meta 失败 key=%s error=%s", key, e, exc_info=True)
        return {}, False, False
    except Exception as e:
        logger.error("R2 read conversation_meta 失败 key=%s error=%s", key, e, exc_info=True)
        return {}, False, False


def _read_conversation_meta(client, window_id: str) -> dict:
    meta, _, _ = _read_conversation_meta_status(client, window_id)
    return meta


def _read_recent_rounds(client, window_id: str) -> list[dict]:
    data = _read_json(client, _conversation_recent_key(window_id))
    rounds = data.get("rounds") if isinstance(data, dict) else []
    return _sort_rounds(rounds if isinstance(rounds, list) else [])


def _write_compact_conversation_state_from_rounds(
    client,
    window_id: str,
    rounds: list[dict],
    *,
    write_recent_round_files: bool = False,
) -> dict:
    sorted_rounds = _sort_rounds(rounds)
    max_idx = max((_round_index_value(r) for r in sorted_rounds), default=0)
    recent = sorted_rounds[-CONVERSATION_RECENT_MAX_ROUNDS:]
    now = now_beijing_iso()
    meta = {
        "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
        "window_id": normalize_window_id(window_id),
        "last_round_index": max_idx,
        "next_round_index": max_idx + 1 if max_idx > 0 else 1,
        "round_count": len(sorted_rounds),
        "recent_keep": CONVERSATION_RECENT_MAX_ROUNDS,
        "updated_at": now,
    }
    recent_payload = {
        "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
        "window_id": normalize_window_id(window_id),
        "rounds": recent,
        "updated_at": now,
    }
    _write_json(client, _conversation_recent_key(window_id), recent_payload)
    _write_json(client, _conversation_meta_key(window_id), meta)
    if write_recent_round_files:
        for r in recent:
            idx = _round_index_value(r)
            if idx > 0:
                _write_json(client, _conversation_round_key(window_id, idx), r)
    return meta


def _repair_compact_conversation_state_from_recent_sources(client, window_id: str, meta: dict) -> dict:
    recent = _read_recent_rounds(client, window_id)
    backup_rounds = _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates())
    merged = _merge_rounds_by_index([recent, backup_rounds])
    merged_max = max((_round_index_value(r) for r in merged), default=0)
    try:
        meta_last = int((meta or {}).get("last_round_index") or 0)
    except Exception:
        meta_last = 0
    if merged_max <= meta_last:
        return meta or _empty_conversation_meta(window_id)
    logger.warning(
        "conversation compact meta 落后，自动修正 window_id=%s meta_last=%s detected_max=%s",
        window_id,
        meta_last,
        merged_max,
    )
    return _write_compact_conversation_state_from_rounds(
        client,
        window_id,
        merged,
        write_recent_round_files=False,
    )


def _ensure_compact_conversation_state(client, window_id: str) -> dict:
    meta, read_ok, missing = _read_conversation_meta_status(client, window_id)
    if meta:
        return _repair_compact_conversation_state_from_recent_sources(client, window_id, meta)

    if not read_ok:
        logger.warning("conversation compact meta 读取失败，跳过 legacy bootstrap window_id=%s", window_id)
        meta = _empty_conversation_meta(window_id)
        meta["read_failed"] = True
        return meta

    recent = _read_recent_rounds(client, window_id)
    backup_rounds = _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates())
    rounds = _merge_rounds_by_index([recent, backup_rounds])
    try:
        if rounds:
            meta = _write_compact_conversation_state_from_rounds(
                client,
                window_id,
                rounds,
                write_recent_round_files=False,
            )
        else:
            meta = _empty_conversation_meta(window_id)
            _write_json(client, _conversation_meta_key(window_id), meta)
    except Exception as e:
        sorted_rounds = _sort_rounds(rounds)
        max_idx = max((_round_index_value(r) for r in sorted_rounds), default=0)
        meta = {
            "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
            "window_id": normalize_window_id(window_id),
            "last_round_index": max_idx,
            "next_round_index": max_idx + 1 if max_idx > 0 else 1,
            "round_count": len(sorted_rounds),
            "recent_keep": CONVERSATION_RECENT_MAX_ROUNDS,
            "updated_at": now_beijing_iso(),
            "bootstrap_write_failed": True,
        }
        logger.warning("conversation compact bootstrap 写入失败 window_id=%s error=%s", window_id, e, exc_info=True)
    logger.info(
        "conversation compact bootstrap window_id=%s missing=%s rounds=%s last_round_index=%s",
        window_id,
        missing,
        len(rounds),
        meta.get("last_round_index"),
    )
    return meta


def _read_conversation_data_with_legacy_migrate(window_id: str) -> dict:
    """
    读取主存 conversation.json；若默认窗口在新路径无数据而 legacy（windows//）有，则迁移到新路径后返回。
    """
    client = _s3_client()
    if not client:
        return {}
    wid = normalize_window_id(window_id)
    prefix = _prefix(wid)
    key = _get_key(prefix, "conversation.json")
    data = _read_json(client, key) or {}
    rounds = data.get("rounds")
    if isinstance(rounds, list) and len(rounds) > 0:
        return data
    if wid == WINDOW_ID_DEFAULT:
        legacy = _read_json(client, LEGACY_EMPTY_CONVERSATION_KEY) or {}
        leg_rounds = legacy.get("rounds")
        if isinstance(leg_rounds, list) and len(leg_rounds) > 0:
            try:
                _write_json(client, key, legacy)
                logger.info("已迁移对话主存 %s -> %s", LEGACY_EMPTY_CONVERSATION_KEY, key)
            except Exception as e:
                logger.error("迁移 legacy 对话失败 error=%s", e, exc_info=True)
                return legacy
            return legacy
    return data


def _conversations_key_for_date(window_id: str, date: str) -> str:
    """conversations/日期/window_<id>.json，用于按日期备份。"""
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in normalize_window_id(window_id))
    return f"conversations/{date}/window_{safe_id}.json"


def append_conversation_round(window_id: str, round_index: int, messages: list, timestamp: str = "", action_note: str = "") -> bool:
    """
    追加一轮对话原文。
    ① 写 windows/<id>/rounds/<index>.json（单轮存档）
    ② 滚动写 windows/<id>/recent_rounds.json（热路径最近 N 轮）
    ③ 写 windows/<id>/conversation_meta.json（下一轮 index）
    ④ 写 conversations/YYYY-MM-DD/window_<id>.json（按日期备份，与文档一致）
    """
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 append_conversation_round window_id=%s", window_id)
        logger.info("R2 未存档：未配置 R2 凭证（R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY）")
        return False
    try:
        wid_norm = normalize_window_id(window_id)
        ts = (timestamp or "").strip() or now_beijing_iso()
        round_entry = {"index": round_index, "timestamp": ts, "messages": messages}
        if str(action_note or "").strip():
            round_entry["action_note"] = str(action_note).strip()
        with _conversation_write_lock:
            meta = _ensure_compact_conversation_state(client, window_id)
            guard_rounds = _merge_rounds_by_index(
                [
                    _read_recent_rounds(client, window_id),
                    _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates()),
                ]
            )
            guard_max = max((_round_index_value(r) for r in guard_rounds), default=0)
            if meta.get("read_failed") and guard_max <= 0:
                logger.error(
                    "append_conversation_round 终止：compact meta 读取失败且无 guard 来源 window_id=%s round_index=%s",
                    window_id,
                    round_index,
                )
                return False
            if int(round_index or 0) <= guard_max:
                logger.warning(
                    "append_conversation_round 收到非递增 round_index window_id=%s round_index=%s guard_max=%s",
                    window_id,
                    round_index,
                    guard_max,
                )
            if not conversation_sqlite_store.has_window(window_id):
                try:
                    conversation_sqlite_store.import_window_state(
                        wid_norm,
                        guard_rounds,
                        meta,
                        recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
                    )
                except Exception as e:
                    logger.warning("append_conversation_round sqlite bootstrap 失败 window_id=%s error=%s", window_id, e)
            round_key = _conversation_round_key(window_id, round_index)
            _write_json(client, round_key, round_entry)

            recent = guard_rounds
            recent = [r for r in recent if _round_index_value(r) != int(round_index)]
            recent.append(round_entry)
            recent = _latest_rounds(recent, CONVERSATION_RECENT_MAX_ROUNDS)
            now = now_beijing_iso()
            _write_json(
                client,
                _conversation_recent_key(window_id),
                {
                    "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
                    "window_id": wid_norm,
                    "rounds": recent,
                    "updated_at": now,
                },
            )

            last_idx = max(int(meta.get("last_round_index") or 0), int(round_index or 0))
            round_count = int(meta.get("round_count") or 0)
            if int(round_index or 0) > int(meta.get("last_round_index") or 0):
                round_count += 1
            meta.update(
                {
                    "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
                    "window_id": wid_norm,
                    "last_round_index": last_idx,
                    "next_round_index": last_idx + 1 if last_idx > 0 else 1,
                    "round_count": max(round_count, len(recent)),
                    "recent_keep": CONVERSATION_RECENT_MAX_ROUNDS,
                    "updated_at": now,
                }
            )
            _write_json(client, _conversation_meta_key(window_id), meta)

            # 按日期备份到 conversations/（文档十一：原文存档）。日备份通常很小，保留兼容。
            today = today_beijing()
            conv_key = _conversations_key_for_date(window_id, today)
            conv_existing = _read_json(client, conv_key)
            if conv_existing is None:
                conv_existing = {"window_id": wid_norm, "date": today, "rounds": []}
            conv_existing.setdefault("rounds", []).append(round_entry)
            _write_json(client, conv_key, conv_existing)
            try:
                conversation_sqlite_store.upsert_round(
                    wid_norm,
                    round_entry,
                    recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
                )
            except Exception as e:
                logger.warning("append_conversation_round sqlite 同步失败 window_id=%s round_index=%s error=%s", window_id, round_index, e)
        try:
            from storage import chat_activity_store

            chat_activity_store.append_chat_activity_round(wid_norm, ts, round_entry.get("messages") or [])
        except Exception as e:
            logger.warning("chat_activity_context 增量统计失败 window_id=%s round_index=%s error=%s", window_id, round_index, e)
        logger.info("R2 已写入 对话轮次 window_id=%s round_index=%s key=%s", window_id, round_index, round_key)
        return True
    except Exception as e:
        logger.error("append_conversation_round 失败 window_id=%s round_index=%s error=%s", window_id, round_index, e, exc_info=True)
        return False

def overwrite_conversation_rounds(window_id: str, rounds: list[dict]) -> bool:
    """
    覆盖写入某个窗口的 compact 对话存档，用于重放/纠偏。
    - rounds 结构需为 [{ "index": int, "messages": [...] }, ...]。
    - 不改 conversations/YYYY-MM-DD/ 下面的按日备份（避免误删历史备份）。
    """
    client = _s3_client()
    if not client:
        logger.warning("R2 client 未配置，跳过 overwrite_conversation_rounds window_id=%s", window_id)
        return False
    try:
        _write_compact_conversation_state_from_rounds(
            client,
            window_id,
            rounds or [],
            write_recent_round_files=True,
        )
        try:
            client.delete_object(Bucket=R2_BUCKET_NAME, Key=_get_key(_prefix(window_id), "conversation.json"))
        except Exception as e:
            logger.warning("overwrite_conversation_rounds 删除 legacy conversation.json 失败 window_id=%s error=%s", window_id, e)
        try:
            conversation_sqlite_store.replace_window_rounds(
                normalize_window_id(window_id),
                rounds or [],
                recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
            )
        except Exception as e:
            logger.warning("overwrite_conversation_rounds sqlite 同步失败 window_id=%s error=%s", window_id, e)
        logger.info(
            "overwrite_conversation_rounds 完成 window_id=%s rounds=%s compact_only=True",
            window_id,
            len(rounds or []),
        )
        return True
    except Exception as e:
        logger.error("overwrite_conversation_rounds 失败 window_id=%s error=%s", window_id, e, exc_info=True)
        return False


def get_next_round_index(window_id: str) -> int:
    """
    根据轻量 meta 计算下一轮应使用的 round index（从 1 起）。
    meta 缺失时只做一次 legacy bootstrap，避免每轮读取完整 conversation.json。
    """
    client = _s3_client()
    if not client:
        return 1
    meta = _ensure_compact_conversation_state(client, window_id)
    recent = _read_recent_rounds(client, window_id)
    backup_rounds = _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates())
    guard_max = max((_round_index_value(r) for r in (recent + backup_rounds)), default=0)
    try:
        next_idx = int(meta.get("next_round_index") or 0)
    except Exception:
        next_idx = 0
    try:
        last_idx = int(meta.get("last_round_index") or 0)
    except Exception:
        last_idx = 0
    max_idx = max(last_idx, guard_max)
    if meta.get("read_failed") and guard_max <= 0:
        raise RuntimeError(f"conversation compact meta read failed for window_id={window_id}")
    if guard_max > last_idx:
        now = now_beijing_iso()
        repaired = dict(meta or _empty_conversation_meta(window_id))
        repaired.update(
            {
                "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
                "window_id": normalize_window_id(window_id),
                "last_round_index": guard_max,
                "next_round_index": guard_max + 1,
                "recent_keep": CONVERSATION_RECENT_MAX_ROUNDS,
                "updated_at": now,
            }
        )
        try:
            _write_json(client, _conversation_meta_key(window_id), repaired)
            logger.warning(
                "get_next_round_index 已修正倒退 meta window_id=%s meta_last=%s guard_max=%s",
                window_id,
                last_idx,
                guard_max,
            )
        except Exception as e:
            logger.warning("get_next_round_index 修正 meta 失败 window_id=%s error=%s", window_id, e)
    try:
        conversation_sqlite_store.import_window_state(
            normalize_window_id(window_id),
            _merge_rounds_by_index([recent, backup_rounds]),
            {**(meta or {}), "last_round_index": max_idx, "next_round_index": max_idx + 1},
            recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
        )
    except Exception as e:
        logger.warning("get_next_round_index sqlite bootstrap 失败 window_id=%s error=%s", window_id, e)
    return max(next_idx, max_idx + 1, 1)


def get_conversation_rounds(window_id: str, last_n: int = 4) -> list:
    """获取该窗口最近 N 轮对话原文。热路径走 recent_rounds.json，不读整包 conversation.json。"""
    try:
        n = int(last_n or 0)
    except Exception:
        n = 0
    if n <= 0:
        return []
    sqlite_meta = conversation_sqlite_store.get_window_meta(window_id)
    sqlite_rounds = conversation_sqlite_store.get_rounds(window_id, last_n=n)
    if sqlite_rounds:
        try:
            sqlite_round_count = int((sqlite_meta or {}).get("round_count") or len(sqlite_rounds))
        except Exception:
            sqlite_round_count = len(sqlite_rounds)
        try:
            sqlite_recent_keep = int((sqlite_meta or {}).get("recent_keep") or 0)
        except Exception:
            sqlite_recent_keep = 0
        sqlite_retention_limit = conversation_sqlite_store.max_rounds_per_window(sqlite_recent_keep)
        expected = min(n, max(0, sqlite_round_count), max(1, sqlite_retention_limit))
        if len(sqlite_rounds) >= max(1, expected):
            return sqlite_rounds
    client = _s3_client()
    if not client:
        return []
    meta = _ensure_compact_conversation_state(client, window_id)
    recent = _read_recent_rounds(client, window_id)
    backup_rounds = _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates())
    merged_recent = _merge_rounds_by_index([recent, backup_rounds])
    try:
        conversation_sqlite_store.import_window_state(
            normalize_window_id(window_id),
            merged_recent,
            meta,
            recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
        )
    except Exception as e:
        logger.warning("get_conversation_rounds sqlite bootstrap 失败 window_id=%s error=%s", window_id, e)
    if merged_recent and n <= CONVERSATION_RECENT_MAX_ROUNDS:
        return _latest_rounds(merged_recent, n)
    if recent and n <= CONVERSATION_RECENT_MAX_ROUNDS:
        return _latest_rounds(recent, n)

    if n <= CONVERSATION_RECENT_MAX_ROUNDS:
        return []

    # 大范围管理视图也不再回退 legacy conversation.json；旧整包已证明会污染 compact。
    return _latest_rounds(merged_recent, n)


def get_conversation_round_by_index(window_id: str, round_index: int) -> Optional[dict]:
    """读取该窗口指定 index 的轮次（返回 {index,timestamp,messages} 或 None）。"""
    if round_index < 1:
        return None
    client = _s3_client()
    if not client:
        return None
    compact_round = _read_json(client, _conversation_round_key(window_id, round_index))
    if isinstance(compact_round, dict) and _round_index_value(compact_round) == round_index:
        if conversation_sqlite_store.has_window(window_id):
            try:
                conversation_sqlite_store.upsert_round(
                    normalize_window_id(window_id),
                    compact_round,
                    recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
                )
            except Exception as e:
                logger.warning("get_conversation_round_by_index sqlite 同步失败 window_id=%s index=%s error=%s", window_id, round_index, e)
        return compact_round
    for r in _read_recent_rounds(client, window_id):
        if _round_index_value(r) == round_index:
            if conversation_sqlite_store.has_window(window_id):
                try:
                    conversation_sqlite_store.upsert_round(
                        normalize_window_id(window_id),
                        r,
                        recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
                    )
                except Exception as e:
                    logger.warning("get_conversation_round_by_index recent sqlite 同步失败 window_id=%s index=%s error=%s", window_id, round_index, e)
            return r
    for r in _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates(14)):
        if _round_index_value(r) == round_index:
            if conversation_sqlite_store.has_window(window_id):
                try:
                    conversation_sqlite_store.upsert_round(
                        normalize_window_id(window_id),
                        r,
                        recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
                    )
                except Exception as e:
                    logger.warning("get_conversation_round_by_index backup sqlite 同步失败 window_id=%s index=%s error=%s", window_id, round_index, e)
            return r
    return None


def get_pseudo_cot_state(window_id: str = "") -> dict:
    client = _s3_client()
    if not client:
        return {}
    data = _read_json(client, _pseudo_cot_state_key(window_id))
    return data if isinstance(data, dict) else {}


def save_pseudo_cot_state(window_id: str, state: dict) -> bool:
    client = _s3_client()
    if not client:
        return False
    payload = dict(state or {})
    payload["window_id"] = normalize_window_id(window_id)
    try:
        _write_json(client, _pseudo_cot_state_key(window_id), payload)
        return True
    except Exception as e:
        logger.error("save_pseudo_cot_state 失败 window_id=%s error=%s", window_id, e, exc_info=True)
        return False


def _content_to_text_for_preview(content) -> str:
    """把 message content（str 或 list of parts）尽量转成纯文本，用于管理端预览。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                else:
                    parts.append(f"[{c.get('type', '')}]")
            else:
                parts.append(str(c))
        return " ".join(parts).strip()
    return str(content).strip()


def list_conversation_rounds_preview(window_id: str, preview_chars: int = 24) -> list[dict]:
    """
    列出该窗口所有轮次的序号 + 前几个字预览（便于管理端定位 round_index）。
    返回：[{ "index": 1, "preview": "user:... | assistant:..." }, ...]
    """
    client = _s3_client()
    if not client:
        return []
    recent = _read_recent_rounds(client, window_id)
    backup_rounds = _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates(14))
    merged = _merge_rounds_by_index([recent, backup_rounds])
    try:
        conversation_sqlite_store.import_window_state(
            normalize_window_id(window_id),
            merged,
            _ensure_compact_conversation_state(client, window_id),
            recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
        )
    except Exception as e:
        logger.warning("list_conversation_rounds_preview sqlite bootstrap 失败 window_id=%s error=%s", window_id, e)
    by_idx: dict[int, dict] = {}
    for r in merged:
        idx = _round_index_value(r)
        if idx > 0:
            by_idx[idx] = r

    out: list[dict] = []
    for r in by_idx.values():
        idx = r.get("index")
        msgs = r.get("messages") or []
        user_text = ""
        asst_text = ""
        for m in msgs:
            role = (m.get("role") or "").lower()
            t = _content_to_text_for_preview(m.get("content"))
            if role == "user" and not user_text:
                user_text = t
            if role == "assistant" and not asst_text:
                asst_text = t
        preview = f"user:{user_text} | assistant:{asst_text}".strip()
        preview = preview.replace("\n", " ").replace("\r", " ")
        if preview_chars and preview_chars > 0 and len(preview) > preview_chars:
            preview = preview[:preview_chars] + "…"
        out.append({"index": idx, "preview": preview})

    # 按 index 升序
    out.sort(key=lambda x: (x.get("index") or 0))
    return out


def delete_conversation_round(window_id: str, round_index: int) -> bool:
    """
    从该窗口存档中删除指定轮次（老婆在 RikkaHub 删掉该轮后，记忆系统同步删除）。
    删除：
    1) compact 单轮 windows/<id>/rounds/<index>.json
    2) 按日期备份 conversations/YYYY-MM-DD/window_<id>.json（全量回溯，最佳努力）
    """
    client = _s3_client()
    if not client:
        return False
    try:
        compact_deleted = False
        try:
            client.delete_object(Bucket=R2_BUCKET_NAME, Key=_conversation_round_key(window_id, round_index))
            compact_deleted = True
        except Exception as e:
            logger.warning("delete_conversation_round compact 单轮删除失败 window_id=%s round_index=%s error=%s", window_id, round_index, e)

        recent = _read_recent_rounds(client, window_id)
        if recent:
            next_recent = [r for r in recent if _round_index_value(r) != round_index]
            if len(next_recent) != len(recent):
                _write_json(
                    client,
                    _conversation_recent_key(window_id),
                    {
                        "schema_version": CONVERSATION_COMPACT_SCHEMA_VERSION,
                        "window_id": normalize_window_id(window_id),
                        "rounds": next_recent[-CONVERSATION_RECENT_MAX_ROUNDS:],
                        "updated_at": now_beijing_iso(),
                    },
                )
                compact_deleted = True

        # 回溯删除 conversations/ 下按日期备份
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in normalize_window_id(window_id))
        suffix = f"/window_{safe_id}.json"
        token = None
        deleted_backup_files = 0
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": "conversations/"}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in (resp.get("Contents") or []):
                k = obj.get("Key") or ""
                if not k.endswith(suffix):
                    continue
                conv_data = _read_json(client, k)
                if not conv_data or not conv_data.get("rounds"):
                    continue
                before = len(conv_data.get("rounds") or [])
                conv_data["rounds"] = [r for r in conv_data["rounds"] if r.get("index") != round_index]
                after = len(conv_data["rounds"])
                if after != before:
                    _write_json(client, k, conv_data)
                    deleted_backup_files += 1
                    compact_deleted = True
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
        merged = _merge_rounds_by_index(
            [
                _read_recent_rounds(client, window_id),
                _read_conversation_backup_rounds_for_dates(client, window_id, _conversation_guard_dates()),
            ]
        )
        if merged:
            _write_compact_conversation_state_from_rounds(
                client,
                window_id,
                merged,
                write_recent_round_files=False,
            )
            try:
                conversation_sqlite_store.replace_window_rounds(
                    normalize_window_id(window_id),
                    merged,
                    recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
                )
            except Exception as e:
                logger.warning("delete_conversation_round sqlite replace 失败 window_id=%s round_index=%s error=%s", window_id, round_index, e)
        else:
            _write_json(client, _conversation_meta_key(window_id), _empty_conversation_meta(window_id))
            try:
                conversation_sqlite_store.replace_window_rounds(
                    normalize_window_id(window_id),
                    [],
                    recent_keep=CONVERSATION_RECENT_MAX_ROUNDS,
                )
            except Exception as e:
                logger.warning("delete_conversation_round sqlite clear 失败 window_id=%s round_index=%s error=%s", window_id, round_index, e)
        logger.info(
            "delete_conversation_round 已删除 window_id=%s round_index=%s backup_files=%s",
            window_id,
            round_index,
            deleted_backup_files,
        )
        return True
    except Exception as e:
        logger.error("delete_conversation_round 失败 window_id=%s round_index=%s error=%s", window_id, round_index, e, exc_info=True)
        return False
