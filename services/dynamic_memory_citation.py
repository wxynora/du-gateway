from __future__ import annotations

import re
from typing import Any


DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY = "_du_dynamic_memory_citation_map"

_CITATION_RE = re.compile(r"\[\s*memory\s+([0-9][0-9,\s]*)\s*\]", re.IGNORECASE)


def normalize_citation_map(citation_map: Any) -> dict[str, str]:
    if not isinstance(citation_map, dict):
        return {}
    out: dict[str, str] = {}
    for label, memory_id in citation_map.items():
        label_s = str(label or "").strip()
        memory_id_s = str(memory_id or "").strip()
        if not label_s.isdigit() or not memory_id_s or memory_id_s.startswith("core::"):
            continue
        out[label_s] = memory_id_s
    return out


def strip_assistant_memory_citations(text: str, citation_map: Any) -> tuple[str, list[str]]:
    """
    剥离动态记忆引用标记，如 [memory 1] / [memory 1, 2]。
    返回 (可见文本, 被引用的 memory_id 列表)。
    """
    if not text:
        return text or "", []
    cmap = normalize_citation_map(citation_map)
    if not cmap:
        return text, []

    referenced_ids: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(1) or ""
        labels = re.findall(r"\d+", raw)
        if not labels or any(label not in cmap for label in labels):
            return match.group(0)
        for label in labels:
            mid = cmap.get(label)
            if mid:
                referenced_ids.append(mid)
        return ""

    visible = _CITATION_RE.sub(_replace, text)
    referenced_ids = _dedupe(referenced_ids)
    if not referenced_ids:
        return text, []
    visible = re.sub(r"[ \t]+([,，.。!！?？;；:：])", r"\1", visible)
    visible = re.sub(r"([（(])\s+", r"\1", visible)
    visible = re.sub(r"[ \t]{2,}", " ", visible)
    visible = re.sub(r"\n{3,}", "\n\n", visible)
    return visible.strip(), referenced_ids


def compute_visible_streaming(text: str, citation_map: Any) -> str:
    """
    流式输出时隐藏已闭合或正在生成中的 [memory 1] 记忆引用。
    """
    if not text:
        return ""
    cmap = normalize_citation_map(citation_map)
    if not cmap:
        return text

    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "[":
            out.append(ch)
            i += 1
            continue
        end = text.find("]", i + 1)
        if end < 0:
            tail = text[i + 1 :]
            if _is_partial_memory_citation(tail):
                return "".join(out).rstrip()
            out.append(ch)
            i += 1
            continue
        raw = text[i + 1 : end]
        m = re.fullmatch(r"\s*memory\s+([0-9][0-9,\s]*)\s*", raw or "", flags=re.IGNORECASE)
        labels = re.findall(r"\d+", m.group(1)) if m else []
        if labels and all(label in cmap for label in labels):
            i = end + 1
            if out and out[-1].isspace():
                while i < len(text) and text[i] in (" ", "\t"):
                    i += 1
            continue
        out.append(text[i : end + 1])
        i = end + 1
    return "".join(out)


def _is_partial_memory_citation(tail: str) -> bool:
    s = str(tail or "")
    target = "memory "
    low = s.lower()
    if len(low) <= len(target) and target.startswith(low):
        return True
    return bool(re.fullmatch(r"\s*memory\s+[0-9,\s]*", s, flags=re.IGNORECASE))


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
