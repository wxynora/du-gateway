from __future__ import annotations

import json
import logging
from datetime import datetime

import requests
from flask import jsonify, request

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL, TELEGRAM_PROACTIVE_TARGET_USER_ID
from services.chat_tool_helpers import collect_tool_trace_from_messages
from services.dynamic_memory_recall_debug import (
    event_window_id,
    is_live_preview_recall_event,
    merge_citation_events_into_recalls,
    normalize_debug_request_id,
)
from services.reasoning_utils import dedupe_reasoning_text_parts
from storage import r2_store, whitelist_store
from utils.tokens import estimate_tokens

logger = logging.getLogger(__name__)

_REASONING_TRANSLATE_CHUNK_CHARS = 6000
_REASONING_SCAN_ROUNDS_DEFAULT = 80
_REASONING_TARGETS_DEFAULT = 6
_REASONING_TEXT_MAX_CHARS = 60000
_TOOL_ARGUMENTS_MAX_CHARS = 8000
_TOOL_RESULT_MAX_CHARS = 12000
_MEMORY_RECALL_QUERY_MAX_CHARS = 1200
_MEMORY_RECALL_CONTENT_MAX_CHARS = 1200
_MEMORY_RECALL_FALLBACK_MAX_SECONDS = 30 * 60
_SUMITALK_MAIN_WINDOW_ID = "sumitalk-main"
_CLAUDE_PRICE_INPUT_PER_M = 5.0
_CLAUDE_PRICE_CACHE_CREATE_1H_PER_M = 10.0
_CLAUDE_PRICE_CACHE_READ_PER_M = 0.5
_CLAUDE_PRICE_OUTPUT_PER_M = 25.0
_CLAUDE_CACHE_TTL = "1h"
_CLAUDE_FABLE_PRICE_INPUT_PER_M = 10.0
_CLAUDE_FABLE_PRICE_OUTPUT_PER_M = 50.0


def _clip_text(value, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n...（内容过长，已截断 {omitted} 字）"


def _resolve_primary_chat_window_id() -> str:
    recent = whitelist_store.list_recent_windows(limit=200) or []
    for w in recent:
        wid = str((w or {}).get("id") or "").strip()
        if wid.startswith("tg_"):
            return wid
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid > 0:
        return f"tg_{uid}"
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


def _parse_beijing_dt(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(tz=None).astimezone()


def _normalize_cache_debug_items(value) -> list[dict]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if str(item.get("type") or "").strip() in {"text", "output_text", "input_text"}:
                    parts.append(str(item.get("text") or ""))
                elif item.get("content") is not None:
                    parts.append(_content_to_text(item.get("content")))
        return "\n".join(x for x in parts if x)
    return str(content or "")


def _positive_int(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _first_positive_usage_value(usage: dict, keys: tuple[str, ...]) -> int:
    if not isinstance(usage, dict):
        return 0
    for key in keys:
        n = _positive_int(usage.get(key))
        if n > 0:
            return n
    return 0


def _sum_usage_output_tokens(cache_debug_items: list[dict]) -> int:
    total = 0
    for entry in cache_debug_items or []:
        usage = entry.get("usage") if isinstance(entry, dict) else None
        if not isinstance(usage, dict):
            continue
        total += _first_positive_usage_value(usage, ("output_tokens", "completion_tokens"))
    return total


def _sum_usage_thinking_tokens(cache_debug_items: list[dict]) -> tuple[int, bool]:
    total = 0
    has_value = False
    for entry in cache_debug_items or []:
        usage = entry.get("usage") if isinstance(entry, dict) else None
        if not isinstance(usage, dict):
            continue
        if "thinking_tokens" not in usage:
            continue
        try:
            total += max(0, int(float(usage.get("thinking_tokens") or 0)))
            has_value = True
        except Exception:
            continue
    return total, has_value


def _usage_uncached_input_tokens(usage: dict) -> int:
    if not isinstance(usage, dict):
        return 0
    input_tokens = _positive_int(usage.get("input_tokens"))
    if input_tokens:
        return input_tokens
    prompt_tokens = _positive_int(usage.get("prompt_tokens"))
    if not prompt_tokens:
        return 0
    cache_create = _positive_int(usage.get("cache_creation_input_tokens"))
    cache_read = _usage_cache_read_tokens(usage)
    if cache_create or cache_read:
        if prompt_tokens < cache_create + cache_read:
            return prompt_tokens
        return max(0, prompt_tokens - cache_create - cache_read)
    return prompt_tokens


def _usage_cache_read_tokens(usage: dict) -> int:
    if not isinstance(usage, dict):
        return 0
    direct = _positive_int(usage.get("cache_read_input_tokens"))
    if direct:
        return direct
    return _first_positive_usage_value(
        usage,
        ("cached_tokens", "prompt_cached_tokens", "input_cached_tokens"),
    )


def _claude_default_pricing_per_million() -> dict[str, float]:
    return {
        "input": _CLAUDE_PRICE_INPUT_PER_M,
        "cache_creation": _CLAUDE_PRICE_CACHE_CREATE_1H_PER_M,
        "cache_read": _CLAUDE_PRICE_CACHE_READ_PER_M,
        "output": _CLAUDE_PRICE_OUTPUT_PER_M,
    }


def _claude_fable_pricing_per_million() -> dict[str, float]:
    return {
        "input": _CLAUDE_FABLE_PRICE_INPUT_PER_M,
        # Anthropic 1h cache write is 2x input; read is 0.1x input.
        "cache_creation": _CLAUDE_FABLE_PRICE_INPUT_PER_M * 2,
        "cache_read": _CLAUDE_FABLE_PRICE_INPUT_PER_M * 0.1,
        "output": _CLAUDE_FABLE_PRICE_OUTPUT_PER_M,
    }


def _claude_pricing_for_model(model: str) -> dict[str, float]:
    normalized = str(model or "").strip().lower()
    if "fable" in normalized:
        return _claude_fable_pricing_per_million()
    return _claude_default_pricing_per_million()


def _is_claude_cost_model(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    return bool(normalized and ("claude" in normalized or "fable" in normalized))


def _cache_debug_entry_model(entry: dict, usage: dict) -> str:
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    request_info = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    fallback_model = str(usage.get("fallback_model") or "").strip() if isinstance(usage, dict) else ""
    if fallback_model:
        return fallback_model
    candidates = [
        response.get("actual_model"),
        response.get("requested_model"),
        request_info.get("model"),
        entry.get("model"),
    ]
    for candidate in candidates:
        model = str(candidate or "").strip()
        if model:
            return model
    return ""


def _build_cost_line(model: str, usage: dict) -> dict:
    pricing = _claude_pricing_for_model(model)
    input_tokens = _usage_uncached_input_tokens(usage)
    cache_create_tokens = _positive_int(usage.get("cache_creation_input_tokens"))
    cache_read_tokens = _usage_cache_read_tokens(usage)
    output_tokens = _first_positive_usage_value(usage, ("output_tokens", "completion_tokens"))
    input_usd = input_tokens * pricing["input"] / 1_000_000
    cache_create_usd = cache_create_tokens * pricing["cache_creation"] / 1_000_000
    cache_read_usd = cache_read_tokens * pricing["cache_read"] / 1_000_000
    output_usd = output_tokens * pricing["output"] / 1_000_000
    total_usd = input_usd + cache_create_usd + cache_read_usd + output_usd
    return {
        "model": model,
        "pricing_per_million": pricing,
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": cache_create_tokens,
        "cache_read_input_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "input_usd": input_usd,
        "cache_creation_usd": cache_create_usd,
        "cache_read_usd": cache_read_usd,
        "output_usd": output_usd,
        "total_usd": total_usd,
    }


def _build_claude_cost_stats(cache_debug_items: list[dict]) -> dict:
    input_tokens = 0
    cache_create_tokens = 0
    cache_read_tokens = 0
    output_tokens = 0
    usage_entries = 0
    models: list[str] = []
    pricing_by_model: dict[str, dict[str, float]] = {}
    cost_lines: list[dict] = []
    for entry in cache_debug_items or []:
        if not isinstance(entry, dict):
            continue
        usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}
        if not usage or usage.get("usage_returned") is False:
            continue
        model = _cache_debug_entry_model(entry, usage)
        if model and model not in models:
            models.append(model)
        if not _is_claude_cost_model(model):
            continue
        usage_entries += 1
        line = _build_cost_line(model, usage)
        cost_lines.append(line)
        input_tokens += line["input_tokens"]
        cache_create_tokens += line["cache_creation_input_tokens"]
        cache_read_tokens += line["cache_read_input_tokens"]
        output_tokens += line["output_tokens"]
        pricing_by_model[model] = line["pricing_per_million"]
    if usage_entries <= 0:
        return {}
    input_usd = sum(float(line["input_usd"]) for line in cost_lines)
    cache_create_usd = sum(float(line["cache_creation_usd"]) for line in cost_lines)
    cache_read_usd = sum(float(line["cache_read_usd"]) for line in cost_lines)
    output_usd = sum(float(line["output_usd"]) for line in cost_lines)
    total_usd = input_usd + cache_create_usd + cache_read_usd + output_usd
    primary_pricing = dict(cost_lines[-1]["pricing_per_million"]) if cost_lines else _claude_default_pricing_per_million()
    return {
        "provider": "claude",
        "currency": "USD",
        "cache_ttl": _CLAUDE_CACHE_TTL,
        "pricing_per_million": primary_pricing,
        "pricing_per_model": pricing_by_model,
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": cache_create_tokens,
        "cache_read_input_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "input_usd": round(input_usd, 8),
        "cache_creation_usd": round(cache_create_usd, 8),
        "cache_read_usd": round(cache_read_usd, 8),
        "output_usd": round(output_usd, 8),
        "total_usd": round(total_usd, 8),
        "usage_entries": usage_entries,
        "models": models,
        "cost_lines": [
            {
                **line,
                "input_usd": round(float(line["input_usd"]), 8),
                "cache_creation_usd": round(float(line["cache_creation_usd"]), 8),
                "cache_read_usd": round(float(line["cache_read_usd"]), 8),
                "output_usd": round(float(line["output_usd"]), 8),
                "total_usd": round(float(line["total_usd"]), 8),
            }
            for line in cost_lines
        ],
    }


def _build_output_stats(msg: dict, reasoning_text: str, cache_debug_items: list[dict], reasoning_omitted: bool = False) -> dict:
    visible_text = _content_to_text((msg or {}).get("content"))
    visible_tokens_est = estimate_tokens(visible_text)
    reasoning_text_tokens_est = estimate_tokens(reasoning_text)
    usage_output_tokens = _sum_usage_output_tokens(cache_debug_items)
    usage_thinking_tokens, has_usage_thinking_tokens = _sum_usage_thinking_tokens(cache_debug_items)
    if has_usage_thinking_tokens:
        thinking_tokens_source = "usage_output_tokens_details"
        thinking_tokens_est = usage_thinking_tokens
    else:
        thinking_tokens_source = ""
        thinking_tokens_est = 0
    estimated_total = visible_tokens_est + reasoning_text_tokens_est
    output_tokens = usage_output_tokens or estimated_total
    thinking_ratio = (thinking_tokens_est / output_tokens) if output_tokens > 0 else 0
    return {
        "source": "usage" if usage_output_tokens > 0 else "estimate",
        "output_tokens": output_tokens,
        "usage_output_tokens": usage_output_tokens,
        "estimated_output_tokens": estimated_total,
        "visible_tokens_est": visible_tokens_est,
        "reasoning_text_tokens_est": reasoning_text_tokens_est,
        "thinking_tokens_est": thinking_tokens_est,
        "usage_thinking_tokens": usage_thinking_tokens,
        "has_usage_thinking_tokens": has_usage_thinking_tokens,
        "thinking_tokens_source": thinking_tokens_source,
        "thinking_ratio": round(thinking_ratio, 4),
        "reasoning_omitted": bool(reasoning_omitted),
    }


def _extract_reasoning_text_from_message(msg: dict) -> tuple[str, bool]:
    if not isinstance(msg, dict):
        return "", False
    omitted = bool(msg.get("reasoning_omitted") or msg.get("reasoning_details"))

    scalar_text = ""
    for key in ("reasoning", "reasoning_content", "thinking"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            scalar_text = val.strip()
            break

    thinking_block_parts: list[str] = []
    for block in msg.get("thinking_blocks") or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "").strip()
        if btype == "thinking":
            val = block.get("thinking") or block.get("text")
            if isinstance(val, str) and val.strip():
                thinking_block_parts.append(val.strip())
        elif btype == "redacted_thinking":
            omitted = True

    content_parts: list[str] = []
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").strip()
            if btype == "thinking":
                val = block.get("thinking") or block.get("text")
                if isinstance(val, str) and val.strip():
                    content_parts.append(val.strip())
            elif btype == "redacted_thinking":
                omitted = True

    # The archive may retain the same reasoning in multiple wire-format fields.
    # Pick one canonical representation instead of concatenating aliases.
    if scalar_text:
        parts = [scalar_text]
    elif thinking_block_parts:
        parts = thinking_block_parts
    else:
        parts = content_parts
    deduped = dedupe_reasoning_text_parts(parts)
    text = "\n\n".join(deduped).strip()
    return text, omitted


def _format_reasoning_tool_calls(messages: list) -> list[dict]:
    """
    思维链日志展示用：从整轮消息收集所有工具调用和结果。

    旧逻辑只读倒序遇到的第一条 assistant.tool_calls；多轮工具循环时会漏掉前面的调用。
    """
    out: list[dict] = []
    for tc in collect_tool_trace_from_messages(messages or []):
        if not isinstance(tc, dict):
            continue
        tid = str(tc.get("id") or "").strip()
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or tc.get("name") or "").strip()
        args = fn.get("arguments")
        if args is None:
            args = tc.get("arguments")
        if args is None:
            args_text = ""
        elif isinstance(args, str):
            args_text = args
        else:
            try:
                args_text = json.dumps(args, ensure_ascii=False)
            except Exception:
                args_text = str(args)
        result = tc.get("result")
        if result is None:
            result_text = ""
        elif isinstance(result, str):
            result_text = result
        else:
            try:
                result_text = json.dumps(result, ensure_ascii=False)
            except Exception:
                result_text = str(result)
        out.append(
            {
                "id": tid,
                "name": name,
                "arguments": _clip_text(args_text, _TOOL_ARGUMENTS_MAX_CHARS),
                "result": _clip_text(result_text, _TOOL_RESULT_MAX_CHARS),
            }
        )
    return out


def _memory_recall_item_id(item: dict) -> str:
    return str(
        (item or {}).get("memory_id")
        or (item or {}).get("id")
        or (item or {}).get("entry_id")
        or ""
    ).strip()


def _memory_recall_score_id(score: dict) -> str:
    return str((score or {}).get("id") or (score or {}).get("memory_id") or "").strip()


def _slim_memory_recall_score(score: dict) -> dict:
    if not isinstance(score, dict):
        return {}
    out: dict = {}
    for key in (
        "id",
        "memory_id",
        "total",
        "final_total",
        "hybrid_total",
        "sem_user",
        "sem_ctx",
        "bm25",
        "bm25_raw",
        "weight",
        "vector_total",
        "rerank",
        "rerank_rank",
        "rerank_model",
        "rerank_missing",
    ):
        if key in score:
            out[key] = score.get(key)
    if score.get("content"):
        out["content"] = _clip_text(str(score.get("content") or ""), 180)
    if score.get("retrieval_text"):
        out["retrieval_text"] = _clip_text(str(score.get("retrieval_text") or ""), 180)
    return out


def _safe_positive_int(value, fallback: int = 0) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return fallback
    return n if n > 0 else fallback


def _slim_memory_recall_item(item: dict, referenced_ids: set[str], score_by_id: dict[str, dict]) -> dict:
    if not isinstance(item, dict):
        return {}
    mid = _memory_recall_item_id(item)
    out = {
        "id": mid,
        "memory_id": mid,
        "label": str(item.get("label") or "").strip(),
        "source": str(item.get("source") or "").strip(),
        "content": _clip_text(str(item.get("content") or ""), _MEMORY_RECALL_CONTENT_MAX_CHARS),
        "line": _clip_text(str(item.get("line") or ""), _MEMORY_RECALL_CONTENT_MAX_CHARS),
        "tag": str(item.get("tag") or "").strip(),
        "emotion_label": str(item.get("emotion_label") or "").strip(),
        "scene_type": str(item.get("scene_type") or "").strip(),
        "target_type": str(item.get("target_type") or "").strip(),
        "importance": item.get("importance"),
        "mention_count": item.get("mention_count"),
        "created_at": str(item.get("created_at") or "").strip(),
        "updated_at": str(item.get("updated_at") or "").strip(),
        "last_mentioned": str(item.get("last_mentioned") or "").strip(),
        "referenced": bool(mid and mid in referenced_ids),
    }
    if mid and score_by_id.get(mid):
        out["score"] = score_by_id[mid]
    return out


def _slim_memory_recall_event(event: dict, matched_by: str) -> dict:
    if not isinstance(event, dict):
        return {}
    referenced_ids = {
        str(x or "").strip()
        for x in (event.get("referenced_memory_ids") or [])
        if str(x or "").strip()
    }
    score_by_id = {
        sid: _slim_memory_recall_score(score)
        for score in (event.get("scores") or [])
        if isinstance(score, dict) and (sid := _memory_recall_score_id(score))
    }
    recalled_items = [
        _slim_memory_recall_item(item, referenced_ids, score_by_id)
        for item in (event.get("recalled_items") or [])
        if isinstance(item, dict)
    ]
    recalled_lines = []
    for raw in event.get("recalled_lines") or []:
        if isinstance(raw, str):
            recalled_lines.append(_clip_text(raw, _MEMORY_RECALL_CONTENT_MAX_CHARS))
        elif isinstance(raw, dict):
            recalled_lines.append(_clip_text(str(raw.get("content") or raw.get("line") or raw), _MEMORY_RECALL_CONTENT_MAX_CHARS))
    if not recalled_items and event.get("scores"):
        for score in event.get("scores") or []:
            if not isinstance(score, dict):
                continue
            mid = _memory_recall_score_id(score)
            recalled_items.append(
                {
                    "id": mid,
                    "memory_id": mid,
                    "content": _clip_text(str(score.get("content") or score.get("retrieval_text") or ""), _MEMORY_RECALL_CONTENT_MAX_CHARS),
                    "source": "",
                    "referenced": bool(mid and mid in referenced_ids),
                    "score": _slim_memory_recall_score(score),
                }
            )
    return {
        "du_request_id": normalize_debug_request_id(event.get("du_request_id")),
        "timestamp": str(event.get("timestamp") or "").strip(),
        "window_id": event_window_id(event),
        "matched_by": matched_by,
        "query": _clip_text(str(event.get("query") or ""), _MEMORY_RECALL_QUERY_MAX_CHARS),
        "retrieval_query": _clip_text(str(event.get("retrieval_query") or ""), _MEMORY_RECALL_QUERY_MAX_CHARS),
        "keywords": [str(x or "").strip() for x in (event.get("keywords") or []) if str(x or "").strip()][:20],
        "source": str(event.get("source") or "").strip(),
        "reason": str(event.get("reason") or "").strip(),
        "expanded_queries": [
            _clip_text(str(x or ""), _MEMORY_RECALL_QUERY_MAX_CHARS)
            for x in (event.get("expanded_queries") or [])
            if str(x or "").strip()
        ][:6],
        "recalled_count": _safe_positive_int(
            event.get("recalled_count"),
            len(recalled_items) or len(recalled_lines) or 0,
        ),
        "recalled_lines": recalled_lines[:12],
        "recalled_items": recalled_items[:12],
        "referenced_memory_ids": sorted(referenced_ids),
        "referenced_memories": [
            x for x in (event.get("referenced_memories") or []) if isinstance(x, dict)
        ][:12],
        "assistant_preview": _clip_text(str(event.get("assistant_preview") or ""), 240),
        "citation_timestamp": str(event.get("citation_timestamp") or "").strip(),
        "rerank": event.get("rerank") if isinstance(event.get("rerank"), dict) else {},
        "vector_error": str(event.get("vector_error") or "").strip(),
    }


def _load_memory_recall_debug_index(targets: list[str]) -> dict:
    target_set = {str(x or "").strip() for x in targets if str(x or "").strip()}
    if not target_set:
        return {"by_request_id": {}, "by_window": {}}
    try:
        all_events = r2_store.get_dynamic_recall_debug_events(limit=200) or []
    except Exception as e:
        logger.warning("reasoning memory recall debug read failed error=%s", e)
        return {"by_request_id": {}, "by_window": {}}
    events = [e for e in all_events if isinstance(e, dict) and event_window_id(e) in target_set]
    recall_events = [
        e for e in events
        if str((e or {}).get("source") or "").strip() not in ("search_memory", "memory_citation")
        and not is_live_preview_recall_event(e)
    ]
    citation_events = [
        e for e in events
        if str((e or {}).get("source") or "").strip() == "memory_citation"
    ]
    merged = merge_citation_events_into_recalls(recall_events, citation_events)
    by_request_id: dict[str, dict] = {}
    by_window: dict[str, list[dict]] = {}
    for event in merged:
        rid = normalize_debug_request_id(event.get("du_request_id"))
        if rid and rid not in by_request_id:
            by_request_id[rid] = event
        by_window.setdefault(event_window_id(event), []).append(event)
    for values in by_window.values():
        values.sort(key=lambda e: str((e or {}).get("timestamp") or ""), reverse=True)
    return {"by_request_id": by_request_id, "by_window": by_window}


def _find_memory_recall_for_round(
    msg: dict | None,
    window_id: str,
    round_timestamp: str,
    recall_index: dict,
) -> tuple[dict | None, str]:
    if not isinstance(msg, dict):
        return None, ""
    by_request_id = recall_index.get("by_request_id") if isinstance(recall_index, dict) else {}
    by_window = recall_index.get("by_window") if isinstance(recall_index, dict) else {}
    rid = normalize_debug_request_id(msg.get("du_request_id"))
    if rid and isinstance(by_request_id, dict):
        event = by_request_id.get(rid)
        if isinstance(event, dict):
            return event, "du_request_id"

    round_dt = _parse_beijing_dt(round_timestamp)
    if round_dt is None or not isinstance(by_window, dict):
        return None, ""
    candidates = by_window.get(window_id) or []
    for event in candidates:
        event_dt = _parse_beijing_dt(str((event or {}).get("timestamp") or ""))
        if event_dt is None or event_dt > round_dt:
            continue
        try:
            delta = (round_dt - event_dt).total_seconds()
        except Exception:
            continue
        if 0 <= delta <= _MEMORY_RECALL_FALLBACK_MAX_SECONDS:
            return event, "window_time"
    return None, ""


def _split_reasoning_translate_chunks(src: str, max_chars: int = _REASONING_TRANSLATE_CHUNK_CHARS) -> list[str]:
    text = str(src or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > max_chars:
            if current:
                chunks.append("".join(current).strip())
                current = []
                current_len = 0
            for i in range(0, len(line), max_chars):
                part = line[i : i + max_chars].strip()
                if part:
                    chunks.append(part)
            continue
        if current and current_len + len(line) > max_chars:
            chunks.append("".join(current).strip())
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current).strip())
    return [c for c in chunks if c]


def _extract_chat_completion_text(data: dict) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    msg = (choices or [{}])[0].get("message", {}) if isinstance(choices, list) else {}
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts).strip()
    return str(content or "").strip()


def _translate_reasoning_chunk(src: str, url: str, api_key: str, model: str, index: int, total: int) -> str:
    system_prompt = (
        "你是一个高保真翻译器。请把用户提供的 reasoning 或 thinking 全文翻译成简体中文。"
        "必须完整保留原意、顺序与细节，不要总结，不要省略，不要扩写。"
        "代码、函数名、变量名、接口名、JSON 字段名、报错原文、英文专有名词可保留原文。"
        "输出只允许是译文正文，不要加任何前言、标题、注释或解释。"
    )
    if total > 1:
        user_prompt = f"请翻译下面 reasoning 的第 {index}/{total} 段，只输出这一段的译文：\n\n{src}"
    else:
        user_prompt = f"请把下面内容全文翻译成简体中文：\n\n{src}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "thinking": {"type": "disabled"},
        "stream": False,
        "temperature": 0,
        "max_tokens": max(1024, min(8192, len(src) * 3)),
    }
    try:
        rc = requests.post(url, headers=headers, json=body, timeout=90)
        rc.raise_for_status()
        data = rc.json() if rc.content else {}
        out = _extract_chat_completion_text(data)
        if not out:
            raise RuntimeError("上游未返回翻译内容")
        return out
    except requests.HTTPError as e:
        detail = ""
        try:
            detail = (e.response.text or "").strip()
        except Exception:
            detail = ""
        raise RuntimeError(f"翻译请求失败：{detail[:240] or e}")
    except Exception as e:
        raise RuntimeError(f"翻译失败：{e}")


def _translate_reasoning_text(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return ""

    url = str(DEEPSEEK_API_URL or "").strip()
    api_key = str(DEEPSEEK_API_KEY or "").strip()
    model = str(DEEPSEEK_CHAT_MODEL or "").strip()
    if not url or not api_key or not model:
        raise RuntimeError("DeepSeek 翻译未配置完整，无法翻译")

    chunks = _split_reasoning_translate_chunks(src)
    if not chunks:
        return ""
    total = len(chunks)
    translated: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        translated.append(_translate_reasoning_chunk(chunk, url, api_key, model, idx, total))
    return "\n\n".join(part for part in translated if part).strip()


def register_routes(bp) -> None:
    @bp.route("/reasoning/latest", methods=["GET"])
    def miniapp_reasoning_latest():
        """
        返回最新思维链（默认 10 条）：
        - 优先最近窗口里最新的 tg_*
        - 回退最近窗口第一条
        - 返回 reasoning + 工具调用/结果（用于 MiniApp COT 日志展示）
        """
        limit = request.args.get("limit", type=int, default=10)
        if limit < 1:
            limit = 1
        if limit > 30:
            limit = 30
        scan_rounds = request.args.get("scan_rounds", type=int, default=_REASONING_SCAN_ROUNDS_DEFAULT)
        if scan_rounds < 20:
            scan_rounds = 20
        if scan_rounds > 200:
            scan_rounds = 200
        target_limit = request.args.get("windows", type=int, default=_REASONING_TARGETS_DEFAULT)
        if target_limit < 1:
            target_limit = 1
        if target_limit > 20:
            target_limit = 20

        recent = whitelist_store.list_recent_windows(limit=200) or []
        target_candidates: list[str] = []
        for w in recent:
            wid = (w.get("id") or "").strip()
            if not wid:
                continue
            if wid.startswith("tg_") or wid.startswith("wechat_") or wid.startswith("wx_") or wid == _SUMITALK_MAIN_WINDOW_ID:
                if wid not in target_candidates:
                    target_candidates.append(wid)
        if not target_candidates and recent:
            wid0 = (recent[0].get("id") or "").strip()
            if wid0:
                target_candidates = [wid0]

        primary_wid = _resolve_primary_chat_window_id()
        if primary_wid and (primary_wid.startswith("tg_") or primary_wid.startswith("wechat_") or primary_wid.startswith("wx_") or primary_wid == _SUMITALK_MAIN_WINDOW_ID):
            if primary_wid in target_candidates:
                target_candidates.remove(primary_wid)
            target_candidates.insert(0, primary_wid)

        targets = target_candidates[:target_limit]

        if not targets:
            return jsonify({"ok": True, "window_id": "", "items": [], "count": 0})

        memory_recall_index = _load_memory_recall_debug_index(targets)
        out = []
        for target in targets:
            rounds = r2_store.get_conversation_rounds(target, last_n=scan_rounds) or []
            for r in reversed(rounds):
                idx = int(r.get("index") or 0)
                ts = (r.get("timestamp") or "").strip()
                msgs = r.get("messages") or []
                reasoning_text = ""
                reasoning_full_text = ""
                reasoning_omitted = False
                selected_assistant_msg: dict | None = None
                cache_debug_items: list[dict] = []
                tool_calls_out = _format_reasoning_tool_calls(msgs)
                for m in reversed(msgs):
                    role = (m.get("role") or "").strip().lower() if isinstance(m, dict) else ""
                    if role != "assistant":
                        continue
                    if not isinstance(m, dict):
                        continue
                    if selected_assistant_msg is None:
                        selected_assistant_msg = m
                    if not reasoning_text:
                        val, omitted = _extract_reasoning_text_from_message(m)
                        if val:
                            reasoning_full_text = val
                            reasoning_text = _clip_text(val, _REASONING_TEXT_MAX_CHARS)
                        elif omitted:
                            reasoning_omitted = True
                            reasoning_text = "（模型已进行 adaptive thinking，但当前上游未返回可展示的思维链正文）"
                    if not cache_debug_items:
                        cache_debug_items = _normalize_cache_debug_items(m.get("cache_debug"))
                    if (reasoning_text or cache_debug_items) and tool_calls_out:
                        break
                if selected_assistant_msg is not None:
                    output_stats = (
                        _build_output_stats(selected_assistant_msg, reasoning_full_text, cache_debug_items, reasoning_omitted)
                        if selected_assistant_msg
                        else {}
                    )
                    cost_stats = _build_claude_cost_stats(cache_debug_items)
                    recall_event, recall_matched_by = _find_memory_recall_for_round(
                        selected_assistant_msg,
                        target,
                        ts,
                        memory_recall_index,
                    )
                    memory_recall = (
                        _slim_memory_recall_event(recall_event, recall_matched_by)
                        if recall_event and recall_matched_by
                        else None
                    )
                    out.append(
                        {
                            "window_id": target,
                            "index": idx,
                            "timestamp": ts,
                            "reasoning": reasoning_text,
                            "cache_debug": cache_debug_items,
                            "output_stats": output_stats,
                            "cost": cost_stats,
                            "tool_calls": tool_calls_out,
                            "memory_recall": memory_recall,
                            "memory_recall_status": "attached" if memory_recall else "none",
                        }
                    )

        out.sort(
            key=lambda x: (
                _parse_beijing_dt(x.get("timestamp") or "") is not None,
                _parse_beijing_dt(x.get("timestamp") or ""),
            ),
            reverse=True,
        )
        out = out[:limit]
        resp = jsonify(
            {"ok": True, "window_id": targets[0] if targets else "", "window_ids": targets, "items": out, "count": len(out)}
        )
        # 思维链刷新希望“按一下就见效”，这里显式禁缓存，避免移动端/代理命中旧响应。
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @bp.route("/reasoning/translate", methods=["POST"])
    def miniapp_translate_reasoning():
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "text 不能为空"}), 400
        if len(text) > 120000:
            return jsonify({"ok": False, "error": "text 过长，暂不支持翻译"}), 400
        try:
            translated = _translate_reasoning_text(text)
        except Exception as e:
            logger.warning("reasoning_translate_failed length=%s error=%s", len(text), str(e)[:500])
            return jsonify({"ok": False, "error": str(e)}), 502
        return jsonify({"ok": True, "translated": translated})
