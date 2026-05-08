# 表情包：默认分类（代号 key 用于 R2 路径 stickers/{key}/ 与 Telegram 句末 [key]）
# 可在 MiniApp 增加分类，元数据见 R2 stickers/meta.json
import re

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
_TAG_KEYS_CACHE: list[str] = []


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


def cache_sticker_tag_keys_from_meta(meta: dict | None) -> list[str]:
    global _TAG_KEYS_CACHE
    _TAG_KEYS_CACHE = normalize_sticker_tag_keys_from_meta(meta)
    return list(_TAG_KEYS_CACHE)


def get_cached_sticker_tag_keys(refresh: bool = False) -> list[str]:
    if _TAG_KEYS_CACHE and not refresh:
        return list(_TAG_KEYS_CACHE)
    try:
        from storage import r2_store

        return cache_sticker_tag_keys_from_meta(r2_store.get_stickers_meta())
    except Exception:
        return list(_TAG_KEYS_CACHE) if _TAG_KEYS_CACHE else _default_tag_keys()


def sticker_tags_line_for_system_prompt() -> str:
    keys = get_cached_sticker_tag_keys(refresh=False)
    tag_text = " ".join(f"[{k}]" for k in keys)
    return f"当前全部可用英文代号（与 MiniApp/R2 一致，新增分类也会出现在此列表）：{tag_text}"
