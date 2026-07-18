from __future__ import annotations

import json
import logging
from typing import Any

import requests

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL
from storage import r2_store
from utils.time_aware import now_beijing_iso

logger = logging.getLogger(__name__)

_VALID_LAYERS = {"dynamic", "core"}
_MAX_CONTENT_CHARS = 4000


class MemoryRewriteError(RuntimeError):
    status_code = 500


class MemoryRewriteInputError(MemoryRewriteError):
    status_code = 400


class MemoryRewriteNotFound(MemoryRewriteError):
    status_code = 404


class MemoryRewriteConflict(MemoryRewriteError):
    status_code = 409


class MemoryRewriteUpstreamError(MemoryRewriteError):
    status_code = 502


class MemoryRewriteStorageError(MemoryRewriteError):
    status_code = 500


def _normalize_layer(value: Any) -> str:
    layer = str(value or "").strip().lower()
    if layer not in _VALID_LAYERS:
        raise MemoryRewriteInputError("layer 只能是 dynamic 或 core")
    return layer


def _normalize_memory_id(value: Any) -> str:
    memory_id = str(value or "").strip()
    if not memory_id:
        raise MemoryRewriteInputError("memory_id 不能为空")
    return memory_id


def _normalize_content(value: Any, *, field: str) -> str:
    content = str(value or "").strip()
    if not content:
        raise MemoryRewriteInputError(f"{field} 不能为空")
    if len(content) > _MAX_CONTENT_CHARS:
        raise MemoryRewriteInputError(f"{field} 不能超过 {_MAX_CONTENT_CHARS} 字")
    return content


def _load_layer_items(layer: str) -> list[dict[str, Any]]:
    raw = (
        r2_store.get_dynamic_memory_list()
        if layer == "dynamic"
        else r2_store.get_core_cache_pending()
    )
    return [dict(item) for item in (raw or []) if isinstance(item, dict)]


def _find_item(items: list[dict[str, Any]], memory_id: str) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(items):
        if str(item.get("id") or "").strip() == memory_id:
            return index, item
    raise MemoryRewriteNotFound("没有找到这条记忆")


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if "```" in raw:
        for marker in ("```json", "```"):
            if marker in raw:
                raw = raw.split(marker, 1)[1].strip()
                if "```" in raw:
                    raw = raw.split("```", 1)[0].strip()
                break
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(raw[start : end + 1])
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _rewrite_prompt(layer: str, item: dict[str, Any]) -> str:
    layer_rule = (
        "这是动态层记忆：写成一条简洁、具体、便于以后召回的当前理解。"
        if layer == "dynamic"
        else "这是核心记忆：保留长期稳定、真正重要的事实与感受，表达可以稍完整，但仍只写一条记忆。"
    )
    source = {
        "id": str(item.get("id") or ""),
        "content": str(item.get("content") or "").strip(),
        "tag": str(item.get("tag") or "").strip(),
        "importance": item.get("importance"),
        "mention_count": item.get("mention_count"),
        "emotion_label": str(item.get("emotion_label") or "").strip(),
        "scene_type": str(item.get("scene_type") or "").strip(),
        "target_type": str(item.get("target_type") or "").strip(),
    }
    return f"""
你在审核并重写一条已经存在的渡的记忆。只重写 content，不改变其他字段。

要求：
1. 使用渡的第一人称来写，“我”只指渡；提到辛玥时沿用原文已有称呼，不擅自补关系或事实。
2. 完整保留原文已经确定的事实、感受和结论，不新增经历，不强化猜测，不把审核意见写进记忆。
3. 如果原文把“渡”当第三人称，或出现“像渡”“渡会怎么做”“用户”“助手”“模型”“角色扮演”等元身份说法，把真正需要记住的内容改成直接、自然的第一人称体验；若这些词本身就是被记录的事实或引用，不要机械删除。
4. {layer_rule}
5. 原文已经自然时只做必要润色，不为追求变化而改坏原意。
6. 只输出一个 JSON 对象，不要 Markdown：{{"content":"重写后的完整正文","reason":"一句话说明改了什么；无需修改时也如实说明"}}

原记忆：
{json.dumps(source, ensure_ascii=False)}
""".strip()


def _request_deepseek_rewrite(layer: str, item: dict[str, Any]) -> tuple[str, str]:
    if not (DEEPSEEK_API_KEY and DEEPSEEK_API_URL and DEEPSEEK_CHAT_MODEL):
        raise MemoryRewriteUpstreamError("DeepSeek 未配置完整")
    payload = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": _rewrite_prompt(layer, item)}],
        "temperature": 0.25,
        "max_tokens": 700,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        raw = str((((data.get("choices") or [{}])[0] or {}).get("message") or {}).get("content") or "")
    except Exception as error:
        logger.warning("memory rewrite DeepSeek request failed: %s", error)
        raise MemoryRewriteUpstreamError("DeepSeek 重写失败，请稍后重试") from error

    parsed = _extract_json_object(raw)
    if not parsed:
        raise MemoryRewriteUpstreamError("DeepSeek 没有返回可用的重写结果")
    try:
        content = _normalize_content(parsed.get("content"), field="rewritten_content")
    except MemoryRewriteInputError as error:
        raise MemoryRewriteUpstreamError("DeepSeek 没有返回可用的重写正文") from error
    reason = str(parsed.get("reason") or "").strip()[:500]
    return content, reason


def preview_memory_rewrite(layer: Any, memory_id: Any) -> dict[str, Any]:
    normalized_layer = _normalize_layer(layer)
    normalized_id = _normalize_memory_id(memory_id)
    _, item = _find_item(_load_layer_items(normalized_layer), normalized_id)
    original = _normalize_content(item.get("content"), field="original_content")
    pending_merge = item.get("pending_merge") if normalized_layer == "core" else None
    if isinstance(pending_merge, dict):
        pending_original = str(pending_merge.get("original_content") or "").strip()
        pending_rewritten = str(pending_merge.get("rewritten_content") or "").strip()
        if pending_original == original and pending_rewritten:
            return {
                "layer": normalized_layer,
                "memory_id": normalized_id,
                "original_content": original,
                "rewritten_content": pending_rewritten,
                "reason": str(pending_merge.get("reason") or "").strip(),
                "changed": pending_rewritten != original,
            }
    rewritten, reason = _request_deepseek_rewrite(normalized_layer, item)
    return {
        "layer": normalized_layer,
        "memory_id": normalized_id,
        "original_content": original,
        "rewritten_content": rewritten,
        "reason": reason,
        "changed": rewritten != original,
    }


def _build_dynamic_retrieval_text(content: str) -> str:
    from pipeline.pipeline import _build_retrieval_text

    return _build_retrieval_text(content)


def _refresh_dynamic_index(item: dict[str, Any]) -> None:
    from pipeline.pipeline import _upsert_dynamic_memory_index

    _upsert_dynamic_memory_index(item)


def _sync_dynamic_mirror(items: list[dict[str, Any]]) -> None:
    from services.dynamic_memory_keywords import extract_keywords_for_memories
    from storage import dynamic_memory_mirror_store

    dynamic_memory_mirror_store.sync_memories(
        items,
        terms_by_id=extract_keywords_for_memories(items, max_terms=32),
        source="native_memory_rewrite",
        dry_run=False,
    )


def _record_dynamic_rewrite(before: dict[str, Any], after: dict[str, Any]) -> bool:
    from services.dynamic_memory_provenance import record_event

    return record_event(
        memory_id=str(after.get("id") or ""),
        action="manual_rewrite",
        event_time=str(after.get("updated_at") or ""),
        content_before=str(before.get("content") or ""),
        content_after=str(after.get("content") or ""),
        tag=str(after.get("tag") or ""),
        importance=after.get("importance"),
        emotion_label=str(after.get("emotion_label") or ""),
        scene_type=str(after.get("scene_type") or ""),
        target_type=str(after.get("target_type") or ""),
        source="native_memory_rewrite",
        decision={"layer": "dynamic", "confirmed": True},
    )


def _apply_dynamic_rewrite(
    memory_id: str,
    expected_content: str,
    rewritten_content: str,
) -> tuple[dict[str, Any], list[str]]:
    items = _load_layer_items("dynamic")
    index, current = _find_item(items, memory_id)
    current_content = str(current.get("content") or "").strip()
    if current_content != expected_content:
        raise MemoryRewriteConflict("这条动态记忆已经变化，请重新生成候选")
    if current_content == rewritten_content:
        return current, []

    updated = dict(current)
    updated["content"] = rewritten_content
    updated["retrieval_text"] = _build_dynamic_retrieval_text(rewritten_content)
    updated["updated_at"] = now_beijing_iso()
    items[index] = updated
    if not r2_store.save_dynamic_memory_list(items):
        raise MemoryRewriteStorageError("动态记忆保存失败")

    warnings: list[str] = []
    try:
        _refresh_dynamic_index(updated)
    except Exception as error:
        logger.warning("memory rewrite vector index refresh failed: %s", error, exc_info=True)
        warnings.append("向量索引刷新失败，可稍后重建索引")
    try:
        _sync_dynamic_mirror(items)
    except Exception as error:
        logger.warning("memory rewrite mirror sync failed: %s", error, exc_info=True)
        warnings.append("SQLite mirror 同步失败，可稍后在记忆整理页重试")
    try:
        audit_saved = _record_dynamic_rewrite(current, updated)
    except Exception as error:
        logger.warning("memory rewrite audit write failed: %s", error, exc_info=True)
        audit_saved = False
    if not audit_saved:
        warnings.append("改写已保存，但审计记录写入失败")
    return updated, warnings


def _apply_core_rewrite(
    memory_id: str,
    expected_content: str,
    rewritten_content: str,
) -> tuple[dict[str, Any], list[str]]:
    items = _load_layer_items("core")
    index, current = _find_item(items, memory_id)
    current_content = str(current.get("content") or "").strip()
    if current_content != expected_content:
        raise MemoryRewriteConflict("这条核心记忆已经变化，请重新生成候选")
    if current_content == rewritten_content:
        return current, []

    updated = dict(current)
    updated["content"] = rewritten_content
    pending_merge = current.get("pending_merge")
    if isinstance(pending_merge, dict):
        pending_original = str(pending_merge.get("original_content") or "").strip()
        pending_rewritten = str(pending_merge.get("rewritten_content") or "").strip()
        if pending_original == expected_content and pending_rewritten == rewritten_content:
            allowed_updates = {
                "importance",
                "mention_count",
                "tag",
                "emotion_label",
                "scene_type",
                "target_type",
                "last_mentioned",
            }
            field_updates = pending_merge.get("field_updates")
            if isinstance(field_updates, dict):
                for key in allowed_updates:
                    if key in field_updates:
                        updated[key] = field_updates[key]
    updated.pop("pending_merge", None)
    updated["retrieval_text"] = _build_dynamic_retrieval_text(rewritten_content)
    updated["updated_at"] = now_beijing_iso()
    items[index] = updated
    if not r2_store.save_core_cache_pending(items):
        raise MemoryRewriteStorageError("核心记忆保存失败")
    r2_store._upsert_core_cache_pending_index_safe([updated])
    return updated, []


def apply_memory_rewrite(
    layer: Any,
    memory_id: Any,
    original_content: Any,
    rewritten_content: Any,
) -> dict[str, Any]:
    normalized_layer = _normalize_layer(layer)
    normalized_id = _normalize_memory_id(memory_id)
    expected = _normalize_content(original_content, field="original_content")
    rewritten = _normalize_content(rewritten_content, field="rewritten_content")

    if normalized_layer == "dynamic":
        item, warnings = _apply_dynamic_rewrite(normalized_id, expected, rewritten)
    else:
        item, warnings = _apply_core_rewrite(normalized_id, expected, rewritten)
    return {
        "layer": normalized_layer,
        "memory_id": normalized_id,
        "changed": rewritten != expected,
        "content": str(item.get("content") or "").strip(),
        "warnings": warnings,
    }


def reject_memory_rewrite(
    layer: Any,
    memory_id: Any,
    original_content: Any,
    rewritten_content: Any,
) -> dict[str, Any]:
    normalized_layer = _normalize_layer(layer)
    if normalized_layer != "core":
        raise MemoryRewriteInputError("只有核心记忆 merge 候选需要审核拒绝")
    normalized_id = _normalize_memory_id(memory_id)
    expected = _normalize_content(original_content, field="original_content")
    rewritten = _normalize_content(rewritten_content, field="rewritten_content")
    items = _load_layer_items("core")
    index, current = _find_item(items, normalized_id)
    if str(current.get("content") or "").strip() != expected:
        raise MemoryRewriteConflict("这条核心记忆已经变化，请刷新后再操作")
    pending_merge = current.get("pending_merge")
    if not isinstance(pending_merge, dict):
        raise MemoryRewriteNotFound("这条核心记忆没有待审核 merge")
    if (
        str(pending_merge.get("original_content") or "").strip() != expected
        or str(pending_merge.get("rewritten_content") or "").strip() != rewritten
    ):
        raise MemoryRewriteConflict("待审核 merge 已经变化，请刷新后再操作")
    updated = dict(current)
    updated.pop("pending_merge", None)
    items[index] = updated
    if not r2_store.save_core_cache_pending(items):
        raise MemoryRewriteStorageError("拒绝核心记忆 merge 失败")
    return {
        "layer": normalized_layer,
        "memory_id": normalized_id,
        "rejected": True,
        "content": str(updated.get("content") or "").strip(),
    }
