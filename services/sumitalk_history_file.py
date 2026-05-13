from __future__ import annotations

import json
import os
import threading
from datetime import timedelta
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from config import DATA_DIR
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing


logger = get_logger(__name__)

SUMITALK_HISTORY_FILE = DATA_DIR / "sumitalk_display_histories.json"


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(float(os.environ.get(name, str(default)) or default))
    except Exception:
        value = default
    return max(1, value)


SUMITALK_HISTORY_MAX_ROWS = _positive_int_env("SUMITALK_HISTORY_MAX_ROWS", 80)
SUMITALK_HISTORY_TTL_DAYS = _positive_int_env("SUMITALK_HISTORY_TTL_DAYS", 30)

_cache_lock = threading.Lock()
_cache_sig: tuple[int, int] | None = None
_cache_data: dict = {}


def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return int(st.st_mtime_ns), int(st.st_size)


def load_sumitalk_histories() -> dict:
    """
    Load SumiTalk display history with a tiny mtime/size cache.

    Android fallback polling and realtime fallback both ask for the latest
    message repeatedly. Without this cache, every poll json.loads the whole
    history file even when it has not changed.
    """
    global _cache_sig, _cache_data
    with _cache_lock:
        sig = _file_signature(SUMITALK_HISTORY_FILE)
        if sig is None:
            _cache_sig = None
            _cache_data = {}
            return {}
        if sig == _cache_sig:
            return dict(_cache_data)
        try:
            with SUMITALK_HISTORY_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if not isinstance(data, dict):
                data = {}
        except Exception as e:
            logger.warning("sumitalk history load failed path=%s error=%s", SUMITALK_HISTORY_FILE, e)
            data = {}
        _cache_sig = sig
        _cache_data = data
        return dict(_cache_data)


def save_sumitalk_histories(data: dict) -> bool:
    global _cache_sig, _cache_data
    payload = data if isinstance(data, dict) else {}
    try:
        SUMITALK_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SUMITALK_HISTORY_FILE.with_name(f"{SUMITALK_HISTORY_FILE.name}.{uuid4().hex}.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(SUMITALK_HISTORY_FILE)
        sig = _file_signature(SUMITALK_HISTORY_FILE)
        with _cache_lock:
            _cache_sig = sig
            _cache_data = dict(payload)
        return True
    except Exception as e:
        logger.exception(
            "sumitalk history save failed path=%s rows=%s error=%s",
            SUMITALK_HISTORY_FILE,
            len(payload),
            e,
        )
        return False


def _row_sort_ts(row: dict) -> float:
    raw = str((row or {}).get("updated_at") or "").strip()
    dt = parse_iso_to_beijing(raw)
    return dt.timestamp() if dt else 0.0


def prune_sumitalk_histories(data: dict, keep_keys: Iterable[str] = ()) -> tuple[dict, int]:
    if not isinstance(data, dict):
        return {}, 0
    keep = {str(k or "").strip() for k in keep_keys if str(k or "").strip()}
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    cutoff = now_dt - timedelta(days=SUMITALK_HISTORY_TTL_DAYS) if now_dt else None

    rows: list[tuple[str, dict]] = []
    removed = 0
    for key, row in data.items():
        skey = str(key or "").strip()
        if not skey or not isinstance(row, dict):
            removed += 1
            continue
        updated_dt = parse_iso_to_beijing(str(row.get("updated_at") or "").strip())
        if skey not in keep and cutoff and updated_dt and updated_dt < cutoff:
            removed += 1
            continue
        rows.append((skey, row))

    if len(rows) > SUMITALK_HISTORY_MAX_ROWS:
        keep_rows = [(k, r) for k, r in rows if k in keep]
        other_rows = [(k, r) for k, r in rows if k not in keep]
        other_rows.sort(key=lambda item: _row_sort_ts(item[1]), reverse=True)
        room = max(0, SUMITALK_HISTORY_MAX_ROWS - len(keep_rows))
        kept = keep_rows + other_rows[:room]
        removed += len(rows) - len(kept)
        rows = kept

    return {k: r for k, r in rows}, removed
