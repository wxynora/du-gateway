from __future__ import annotations

import json
import logging
from datetime import datetime

import requests
from flask import jsonify, request

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL, TELEGRAM_PROACTIVE_TARGET_USER_ID
from services.chat_tool_helpers import collect_tool_trace_from_messages
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


def _build_output_stats(msg: dict, reasoning_text: str, cache_debug_items: list[dict], reasoning_omitted: bool = False) -> dict:
    visible_text = _content_to_text((msg or {}).get("content"))
    visible_tokens_est = estimate_tokens(visible_text)
    thinking_tokens_est = estimate_tokens(reasoning_text)
    estimated_total = visible_tokens_est + thinking_tokens_est
    usage_output_tokens = _sum_usage_output_tokens(cache_debug_items)
    output_tokens = usage_output_tokens or estimated_total
    thinking_ratio = (thinking_tokens_est / output_tokens) if output_tokens > 0 else 0
    return {
        "source": "usage" if usage_output_tokens > 0 else "estimate",
        "output_tokens": output_tokens,
        "usage_output_tokens": usage_output_tokens,
        "estimated_output_tokens": estimated_total,
        "visible_tokens_est": visible_tokens_est,
        "thinking_tokens_est": thinking_tokens_est,
        "thinking_ratio": round(thinking_ratio, 4),
        "reasoning_omitted": bool(reasoning_omitted),
    }


def _extract_reasoning_text_from_message(msg: dict) -> tuple[str, bool]:
    if not isinstance(msg, dict):
        return "", False
    parts: list[str] = []
    omitted = bool(msg.get("reasoning_omitted") or msg.get("reasoning_details"))
    for key in ("reasoning", "reasoning_content", "thinking"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    for block in msg.get("thinking_blocks") or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "").strip()
        if btype == "thinking":
            val = block.get("thinking") or block.get("text")
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
        elif btype == "redacted_thinking":
            omitted = True
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").strip()
            if btype == "thinking":
                val = block.get("thinking") or block.get("text")
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
            elif btype == "redacted_thinking":
                omitted = True
    deduped = dedupe_reasoning_text_parts(parts)
    return "\n\n".join(deduped).strip(), omitted


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
            if wid.startswith("tg_") or wid.startswith("wechat_") or wid.startswith("wx_"):
                if wid not in target_candidates:
                    target_candidates.append(wid)
        if not target_candidates and recent:
            wid0 = (recent[0].get("id") or "").strip()
            if wid0:
                target_candidates = [wid0]

        primary_wid = _resolve_primary_chat_window_id()
        if primary_wid and (primary_wid.startswith("tg_") or primary_wid.startswith("wechat_") or primary_wid.startswith("wx_")):
            if primary_wid in target_candidates:
                target_candidates.remove(primary_wid)
            target_candidates.insert(0, primary_wid)

        targets = target_candidates[:target_limit]

        if not targets:
            return jsonify({"ok": True, "window_id": "", "items": [], "count": 0})

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
                if reasoning_text or cache_debug_items or tool_calls_out:
                    output_stats = (
                        _build_output_stats(selected_assistant_msg, reasoning_full_text, cache_debug_items, reasoning_omitted)
                        if selected_assistant_msg
                        else {}
                    )
                    out.append(
                        {
                            "window_id": target,
                            "index": idx,
                            "timestamp": ts,
                            "reasoning": reasoning_text,
                            "cache_debug": cache_debug_items,
                            "output_stats": output_stats,
                            "tool_calls": tool_calls_out,
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
