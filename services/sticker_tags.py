"""Sticker tag validation, shared cache, and prompt rendering."""

import json
import os
import re
import tempfile
import threading

from config import DATA_DIR

DEFAULT_STICKER_TAG_ROWS = [
    {"key": "cute", "label_zh": "可爱"},
    {"key": "pitiful", "label_zh": "可怜"},
    {"key": "affectionate", "label_zh": "深情"},
    {"key": "speechless", "label_zh": "无语"},
    {"key": "angry", "label_zh": "生气"},
    {"key": "sad", "label_zh": "难过"},
    {"key": "happy", "label_zh": "开心"},
    {"key": "shy", "label_zh": "害羞"},
]

# 兼容旧代码：仅含英文代号
STICKER_EMOTION_TAGS = tuple(r["key"] for r in DEFAULT_STICKER_TAG_ROWS)
STICKER_TAGS_SET = frozenset(STICKER_EMOTION_TAGS)
STICKER_TAGS_PROMPT_PREFIX = "当前全部可用英文代号（与 MiniApp/R2 一致，新增分类也会出现在此列表）："
STICKER_TAGS_PROMPT_SHORT_PREFIX = "当前全部可用英文代号："
STICKER_TAGS_PROMPT_PLACEHOLDER = "{sticker_tags}"
_TAG_KEYS_CACHE_FILE = DATA_DIR / "sticker_tag_keys.json"
_TAG_KEYS_CACHE_LOCK = threading.Lock()
_TAG_KEYS_CACHE: list[str] = []
_TAG_KEYS_CACHE_MTIME_NS: int | None = None


def validate_sticker_tag_key(key: str) -> bool:
    """网关统一：小写英文代号，用于 R2 目录与 Telegram [tag]。规则：字母开头，仅 a-z、0-9、下划线，长度 1～64。"""
    k = (key or "").strip().lower()
    if not k or len(k) > 64:
        return False
    return bool(re.match(r"^[a-z][a-z0-9_]*$", k))


def _default_tag_keys() -> list[str]:
    return [str(r.get("key") or "").strip().lower() for r in DEFAULT_STICKER_TAG_ROWS if str(r.get("key") or "").strip()]


def normalize_sticker_tag_keys_from_meta(meta: dict | None) -> list[str]:
    keys = _default_tag_keys()
    if isinstance(meta, dict):
        for it in meta.get("tags") or []:
            if not isinstance(it, dict):
                continue
            k = str(it.get("key") or "").strip().lower()
            if validate_sticker_tag_key(k):
                keys.append(k)
    out: list[str] = []
    seen: set[str] = set()
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _read_shared_tag_keys() -> list[str]:
    global _TAG_KEYS_CACHE, _TAG_KEYS_CACHE_MTIME_NS
    try:
        mtime_ns = _TAG_KEYS_CACHE_FILE.stat().st_mtime_ns
    except OSError:
        return []
    with _TAG_KEYS_CACHE_LOCK:
        if _TAG_KEYS_CACHE and _TAG_KEYS_CACHE_MTIME_NS == mtime_ns:
            return list(_TAG_KEYS_CACHE)
        try:
            payload = json.loads(_TAG_KEYS_CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        raw_keys = payload.get("tags") if isinstance(payload, dict) else None
        if not isinstance(raw_keys, list):
            return []
        keys = normalize_sticker_tag_keys_from_meta(
            {"tags": [{"key": str(key or "")} for key in raw_keys]}
        )
        _TAG_KEYS_CACHE = keys
        _TAG_KEYS_CACHE_MTIME_NS = mtime_ns
        return list(keys)


def _write_shared_tag_keys(keys: list[str]) -> None:
    global _TAG_KEYS_CACHE, _TAG_KEYS_CACHE_MTIME_NS
    _TAG_KEYS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ""
    with _TAG_KEYS_CACHE_LOCK:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=_TAG_KEYS_CACHE_FILE.parent,
                prefix=f".{_TAG_KEYS_CACHE_FILE.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = handle.name
                json.dump({"tags": keys}, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, _TAG_KEYS_CACHE_FILE)
            _TAG_KEYS_CACHE = list(keys)
            _TAG_KEYS_CACHE_MTIME_NS = _TAG_KEYS_CACHE_FILE.stat().st_mtime_ns
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass


def cache_sticker_tag_keys_from_meta(meta: dict | None) -> list[str]:
    keys = normalize_sticker_tag_keys_from_meta(meta)
    _write_shared_tag_keys(keys)
    return list(keys)


def get_cached_sticker_tag_keys(refresh: bool = False) -> list[str]:
    if not refresh:
        shared_keys = _read_shared_tag_keys()
        if shared_keys:
            return shared_keys
        if _TAG_KEYS_CACHE:
            return list(_TAG_KEYS_CACHE)
    try:
        from storage import r2_store

        return cache_sticker_tag_keys_from_meta(r2_store.get_stickers_meta())
    except Exception:
        return list(_TAG_KEYS_CACHE) if _TAG_KEYS_CACHE else _default_tag_keys()


def sticker_tags_line_for_system_prompt() -> str:
    keys = get_cached_sticker_tag_keys(refresh=False)
    tag_text = " ".join(f"[{k}]" for k in keys)
    return f"{STICKER_TAGS_PROMPT_PREFIX}{tag_text}"


def synchronize_sticker_tags_line(prompt_text: str) -> str:
    """Refresh the generated tag line without changing editable prompt text."""
    text = str(prompt_text or "")
    prefixes = sorted(
        (STICKER_TAGS_PROMPT_PREFIX, STICKER_TAGS_PROMPT_SHORT_PREFIX),
        key=len,
        reverse=True,
    )
    pattern = re.compile(
        rf"(?m)^([ \t]*)({'|'.join(re.escape(prefix) for prefix in prefixes)}).*$"
    )
    has_placeholder = STICKER_TAGS_PROMPT_PLACEHOLDER in text
    if not has_placeholder and not pattern.search(text):
        return text
    keys = get_cached_sticker_tag_keys(refresh=False)
    tag_text = " ".join(f"[{key}]" for key in keys)
    text = text.replace(STICKER_TAGS_PROMPT_PLACEHOLDER, tag_text)
    return pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}{tag_text}", text)
