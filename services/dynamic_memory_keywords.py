"""Deterministic keyword extraction for dynamic memory mirrors."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:/+-]{1,}")
_CJK_CHUNK_RE = re.compile(r"[\u4e00-\u9fff]{2,18}")
_SPLIT_RE = re.compile(r"[\s,，。.!！?？;；:：、/\\|()\[\]{}<>《》【】\"'“”‘’]+")

_DOMAIN_PHRASES = (
    "百万计划",
    "动态记忆",
    "近期记忆",
    "核心缓存",
    "思维链",
    "工具循环",
    "窗口总结",
    "离线整理",
    "关键词",
    "召回",
    "文游",
    "小家",
    "卧室",
    "客厅",
    "群聊",
    "小红书",
    "百度网盘",
    "谷歌支付",
    "发卡行",
    "Claude",
    "OpenAI",
    "OpenRouter",
    "DeepSeek",
    "硅基流动",
    "GLM",
    "R2",
    "SQLite",
    "MiniApp",
    "SumiTalk",
    "Telegram",
    "QQ",
    "XiaoAI",
)

_STOP_TERMS = {
    "这个",
    "那个",
    "就是",
    "然后",
    "但是",
    "所以",
    "因为",
    "如果",
    "不是",
    "什么",
    "怎么",
    "现在",
    "时候",
    "可以",
    "一个",
    "一下",
    "没有",
    "还是",
    "应该",
    "感觉",
}

_HASH_FIELDS = (
    "content",
    "retrieval_text",
    "tag",
    "emotion_label",
    "scene_type",
    "target_type",
)


def normalize_term(term: str) -> str:
    raw = str(term or "").strip()
    if not raw:
        return ""
    raw = raw.strip(" \t\r\n,，。.!！?？;；:：、/\\|()[]{}<>《》【】\"'“”‘’")
    if not raw:
        return ""
    if raw.isascii():
        return raw.lower()
    return re.sub(r"\s+", "", raw).lower()


def memory_content_hash(memory: dict[str, Any]) -> str:
    payload = {key: memory.get(key) for key in _HASH_FIELDS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def snapshot_hash(memories: list[dict[str, Any]]) -> str:
    raw = json.dumps({"memories": memories or []}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ids_hash(memories: list[dict[str, Any]]) -> str:
    ids = [str((m or {}).get("id") or "").strip() for m in memories or [] if isinstance(m, dict)]
    raw = json.dumps(ids, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _iter_label_values(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.extend(_iter_label_values(k))
            out.extend(_iter_label_values(v))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            out.extend(_iter_label_values(item))
    elif value is not None:
        text = str(value).strip()
        if text:
            out.append(text)
    return out


def _add_term(
    terms: list[dict[str, Any]],
    seen: set[str],
    term: str,
    *,
    source: str,
    weight: float,
    confidence: float = 1.0,
) -> None:
    clean = str(term or "").strip()
    norm = normalize_term(clean)
    if not norm or norm in _STOP_TERMS or len(norm) < 2:
        return
    if norm in seen:
        return
    seen.add(norm)
    terms.append(
        {
            "term": clean,
            "normalized_term": norm,
            "source": source,
            "weight": float(weight),
            "confidence": float(confidence),
        }
    )


def extract_keywords(memory: dict[str, Any], max_terms: int = 32) -> list[dict[str, Any]]:
    """Extract stable keyword records without changing the memory itself."""
    if not isinstance(memory, dict):
        return []
    terms: list[dict[str, Any]] = []
    seen: set[str] = set()

    for key in ("tag", "emotion_label", "scene_type", "target_type"):
        value = str(memory.get(key) or "").strip()
        if value:
            _add_term(terms, seen, value, source=key, weight=2.0)

    for value in _iter_label_values(memory.get("labels")):
        _add_term(terms, seen, value, source="label", weight=1.8)

    text = "\n".join(
        str(memory.get(key) or "")
        for key in ("content", "retrieval_text")
        if str(memory.get(key) or "").strip()
    )

    for phrase in _DOMAIN_PHRASES:
        if phrase and phrase.lower() in text.lower():
            _add_term(terms, seen, phrase, source="domain_phrase", weight=2.4)

    for token in _ASCII_TOKEN_RE.findall(text):
        _add_term(terms, seen, token, source="ascii_token", weight=1.5)

    for part in _SPLIT_RE.split(text):
        part = part.strip()
        if not part:
            continue
        for chunk in _CJK_CHUNK_RE.findall(part):
            if len(chunk) <= 12:
                _add_term(terms, seen, chunk, source="cjk_phrase", weight=1.0, confidence=0.65)

    terms.sort(key=lambda item: (-float(item.get("weight") or 0), str(item.get("normalized_term") or "")))
    try:
        limit = max(1, int(max_terms or 32))
    except Exception:
        limit = 32
    return terms[:limit]


def extract_keywords_for_memories(
    memories: list[dict[str, Any]],
    max_terms: int = 32,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for memory in memories or []:
        if not isinstance(memory, dict):
            continue
        memory_id = str(memory.get("id") or "").strip()
        if not memory_id:
            continue
        out[memory_id] = extract_keywords(memory, max_terms=max_terms)
    return out
