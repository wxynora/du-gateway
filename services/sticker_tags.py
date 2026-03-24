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


def validate_sticker_tag_key(key: str) -> bool:
    """网关统一：小写英文代号，用于 R2 目录与 Telegram [tag]。规则：字母开头，仅 a-z、0-9、下划线，长度 1～64。"""
    k = (key or "").strip().lower()
    if not k or len(k) > 64:
        return False
    return bool(re.match(r"^[a-z][a-z0-9_]*$", k))
