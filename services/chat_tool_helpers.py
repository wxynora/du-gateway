import copy
import json
import re
import time

from services.reasoning_utils import extract_thinking_from_content
from utils.log import get_logger

logger = get_logger(__name__)

_TOOL_MIDSTREAM_TEXT_RE = re.compile(
    r"(let me (check|look|see|read|inspect)"
    r"|i(?:'|’)ll (check|look|see|read|inspect)"
    r"|guide doesn.?t mention"
    r"|tool description"
    r"|我(?:先|再)?(?:去)?(?:看一下|看看|看一眼|查一下|查查|再看|再查|看下)"
    r"|先看一下"
    r"|先查一下"
    r"|工具说明"
    r"|命令说明)",
    re.IGNORECASE,
)
_TOOL_MIDSTREAM_RETRY_INSTRUCTION = (
    "如果还需要信息，直接继续调用工具；不知道该调用什么工具就直接进行最终回复。\n"
    "如果已经够了，直接继续回应小玥。"
)
_TOOL_EMPTY_FINAL_RETRY_INSTRUCTION = (
    "前面的工具已经执行过了。\n"
    "如果还需要信息，直接继续调用工具；如果已经够了，必须直接给小玥一条可见的回复。\n"
    "不要返回空 content，不要只给 reasoning / thinking。"
)
_TOOL_EVENT_SECRET_RE = re.compile(
    r"(?i)((?:\"|')?(?:api[_-]?key|authorization|cookie|password|passwd|secret|token|access[_-]?token|refresh[_-]?token)(?:\"|')?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^,}\]\s]+)"
)
_TOOL_EVENT_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")


def looks_like_tool_midstream_text(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    visible, thinking = extract_thinking_from_content(raw)
    merged = "\n".join(x for x in (visible.strip(), thinking.strip()) if x).strip() or raw
    merged = " ".join(merged.split()).strip()
    if not merged or len(merged) > 400:
        return False
    if _TOOL_MIDSTREAM_TEXT_RE.search(merged):
        return True
    lower = merged.lower()
    if merged.endswith(("...", "…", "-")) and any(k in lower for k in ("check", "look", "guide", "看看", "查", "说明")):
        return True
    return False


def should_retry_tool_followup(content_text: str, reasoning_text: str = "") -> bool:
    if looks_like_tool_midstream_text(content_text):
        return True
    if not str(content_text or "").strip() and looks_like_tool_midstream_text(reasoning_text):
        return True
    return False


def normalize_visible_reply_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    visible, _thinking = extract_thinking_from_content(raw)
    return visible.strip()


def _tool_round_content_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _tool_round_text_key(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def append_visible_tool_round_content(parts: list[str], content) -> None:
    """
    工具调用中间轮也可能带可见 content；这些 content 需要跟最终回复一起返回给客户端。
    这里先收集正文，去掉 thinking 块，并做轻量去重，避免最终轮已复述时重复刷屏。
    """
    visible = normalize_visible_reply_text(_tool_round_content_text(content))
    key = _tool_round_text_key(visible)
    if not key:
        return
    for idx, existing in enumerate(parts):
        existing_key = _tool_round_text_key(existing)
        if key == existing_key or key in existing_key:
            return
        if existing_key and existing_key in key:
            parts[idx] = visible
            return
    parts.append(visible)


def merge_visible_tool_round_content(prefix_parts: list[str], final_content: str) -> str:
    final = str(final_content or "")
    final_key = _tool_round_text_key(final)
    merged_prefix: list[str] = []
    seen_keys: set[str] = set()
    for part in prefix_parts or []:
        text = normalize_visible_reply_text(part)
        key = _tool_round_text_key(text)
        if not key or key in seen_keys:
            continue
        if final_key and (key == final_key or key in final_key):
            continue
        seen_keys.add(key)
        merged_prefix.append(text)
    if not merged_prefix:
        return final
    final_stripped = final.strip()
    if not final_stripped:
        return "\n\n".join(merged_prefix).strip()
    return "\n\n".join([*merged_prefix, final_stripped]).strip()


def merge_visible_tool_round_content_into_response(resp_json: dict, prefix_parts: list[str]) -> dict:
    if not prefix_parts or not isinstance(resp_json, dict):
        return resp_json
    out = copy.deepcopy(resp_json)
    try:
        choices = out.get("choices") or []
        if not choices:
            return out
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            text_index = None
            for idx, item in enumerate(content):
                if isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "text":
                    text_index = idx
                    break
            if text_index is None:
                msg["content"] = [{"type": "text", "text": merge_visible_tool_round_content(prefix_parts, "")}, *content]
            else:
                item = dict(content[text_index])
                item["text"] = merge_visible_tool_round_content(prefix_parts, item.get("text") or "")
                new_content = list(content)
                new_content[text_index] = item
                msg["content"] = new_content
        else:
            msg["content"] = merge_visible_tool_round_content(prefix_parts, content or "")
        choices[0]["message"] = msg
    except Exception:
        logger.warning("合并工具中间轮正文失败", exc_info=True)
        return resp_json
    return out


def should_retry_tool_empty_final(content_text: str) -> bool:
    return not normalize_visible_reply_text(content_text)


def inject_tool_retry_instruction(body: dict, instruction: str) -> dict:
    body = copy.deepcopy(body)
    messages = list(body.get("messages") or [])
    insert_idx = 0
    while insert_idx < len(messages) and str((messages[insert_idx] or {}).get("role") or "").strip().lower() == "system":
        if str((messages[insert_idx] or {}).get("content") or "").strip() == instruction:
            body["messages"] = messages
            return body
        insert_idx += 1
    messages.insert(
        insert_idx,
        {
            "role": "system",
            "content": instruction,
            "__dynamic__": True,
            "__temporary_dynamic__": True,
        },
    )
    body["messages"] = messages
    return body


def inject_tool_midstream_retry_instruction(body: dict) -> dict:
    return inject_tool_retry_instruction(body, _TOOL_MIDSTREAM_RETRY_INSTRUCTION)


def inject_tool_empty_final_retry_instruction(body: dict) -> dict:
    return inject_tool_retry_instruction(body, _TOOL_EMPTY_FINAL_RETRY_INSTRUCTION)


def _tool_event_text(value, limit: int = 1800) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = _TOOL_EVENT_SECRET_RE.sub(lambda m: f"{m.group(1)}\"***\"" if str(m.group(2) or "").startswith("\"") else f"{m.group(1)}***", text)
    text = _TOOL_EVENT_BEARER_RE.sub("Bearer ***", text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _emit_tool_event(on_tool_event, kind: str, payload: dict) -> None:
    if not on_tool_event:
        return
    try:
        on_tool_event(kind, payload)
    except Exception:
        logger.debug("工具事件回调失败 kind=%s", kind, exc_info=True)


def _last_user_tool_focus(messages: list) -> str:
    for message in reversed(messages or []):
        if not isinstance(message, dict) or str(message.get("role") or "").strip().lower() != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict) or str(item.get("type") or "").strip().lower() not in {"text", "input_text"}:
                    continue
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        return str(content or "").strip()
    return ""


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def append_tool_results_and_continue(
    body: dict,
    assistant_message: dict,
    tool_calls: list,
    execute_tool,
    on_tool_event=None,
    completed_tool_results: list[dict] | None = None,
) -> dict:
    """执行 tool_calls，将 assistant 消息与各 tool 结果追加到 body["messages"]，返回新 body 供继续请求。"""
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    tool_focus = _last_user_tool_focus(messages)
    from config import PUBLIC_REPO_READ_MAX_CHARS

    public_repo_source_limit = int(PUBLIC_REPO_READ_MAX_CHARS)
    public_repo_source_chars = 0
    public_repo_source_items: list[dict] = []
    public_repo_rows: list[dict] = []
    tool_limit_reached = False
    # 保留 assistant 消息（含 tool_calls）
    assistant_trace = {
        "role": "assistant",
        "content": assistant_message.get("content") or None,
        "tool_calls": assistant_message.get("tool_calls"),
    }
    for rk in ("reasoning", "reasoning_content", "thinking", "thinking_blocks", "reasoning_details", "reasoning_omitted"):
        if assistant_message.get(rk):
            assistant_trace[rk] = assistant_message.get(rk)
    messages.append(assistant_trace)
    for tc in tool_calls:
        tid = (tc or {}).get("id") or ""
        fn = (tc or {}).get("function") or {}
        name = fn.get("name") or ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        raw_arguments = fn.get("arguments") or ""
        started_at = time.time()
        base_event = {
            "tool_call_id": tid,
            "name": name,
            "arguments": _tool_event_text(raw_arguments),
        }
        _emit_tool_event(on_tool_event, "tool_call_started", base_event)
        deferred_public_repo_event = False
        public_repo_row: dict | None = None
        if tool_limit_reached:
            result = json.dumps(
                {
                    "ok": False,
                    "action": str(args.get("action") or ""),
                    "repo": str(args.get("repo") or ""),
                    "path": str(args.get("path") or ""),
                    "error_code": "tool_token_limit_reached",
                    "error": f"未执行：本轮仓库工具内容已达到 {public_repo_source_limit} 字符上限",
                    "tool_content_limit_reached": True,
                    "tool_content_limit_chars": public_repo_source_limit,
                    "continue_in_next_user_turn": True,
                },
                ensure_ascii=False,
            )
            _emit_tool_event(on_tool_event, "tool_call_failed", {
                **base_event,
                "ok": False,
                "duration_ms": int((time.time() - started_at) * 1000),
                "error": f"本轮仓库工具内容已达到 {public_repo_source_limit} 字符上限",
                "result_preview": _tool_event_text(result),
            })
        else:
            execution_args = args
            is_public_repo_read = name == "public_repo" and str(args.get("action") or "").strip().lower() == "read"
            if is_public_repo_read:
                execution_args = dict(args)
                execution_args["__du_public_repo_read_max_chars"] = max(
                    1,
                    public_repo_source_limit - public_repo_source_chars,
                )
            try:
                result = execute_tool(name, execution_args)
            except Exception as _tool_exc:
                logger.warning("execute_tool 异常 name=%s error=%s", name, _tool_exc)
                result = json.dumps({"ok": False, "error": f"工具执行异常: {_tool_exc}"}, ensure_ascii=False)
                _emit_tool_event(on_tool_event, "tool_call_failed", {
                    **base_event,
                    "ok": False,
                    "duration_ms": int((time.time() - started_at) * 1000),
                    "error": _tool_event_text(_tool_exc, 500),
                    "result_preview": _tool_event_text(result),
                })
            else:
                result_data = _json_dict(result) if is_public_repo_read else {}
                source_content = result_data.get("content") if result_data.get("ok") is True else None
                if isinstance(source_content, str):
                    visible_data = dict(result_data)
                    visible_data.pop("content", None)
                    visible_data.pop("content_chars", None)
                    visible_data["source_chars"] = len(source_content)
                    result = json.dumps(visible_data, ensure_ascii=False)
                    if source_content:
                        public_repo_source_chars += len(source_content)
                        public_repo_source_items.append(
                            {
                                "repo": str(visible_data.get("repo") or args.get("repo") or ""),
                                "resolved_sha": str(visible_data.get("resolved_sha") or ""),
                                "path": str(visible_data.get("path") or args.get("path") or ""),
                                "line_range": visible_data.get("line_range") if isinstance(visible_data.get("line_range"), dict) else {},
                                "column_range": visible_data.get("column_range") if isinstance(visible_data.get("column_range"), dict) else {},
                                "content": source_content,
                            }
                        )
                        public_repo_row = {
                            "data": visible_data,
                            "base_event": base_event,
                            "started_at": started_at,
                        }
                        deferred_public_repo_event = True
                        if public_repo_source_chars >= public_repo_source_limit:
                            tool_limit_reached = True
                    else:
                        visible_data["source_summary_status"] = "not_needed"
                        visible_data["source_summary"] = "文件内容为空"
                        result = json.dumps(visible_data, ensure_ascii=False)
                if not deferred_public_repo_event:
                    _emit_tool_event(on_tool_event, "tool_call_finished", {
                        **base_event,
                        "ok": True,
                        "duration_ms": int((time.time() - started_at) * 1000),
                        "result_preview": _tool_event_text(result),
                        "result_chars": len(str(result or "")),
                    })
        completed_index = None
        if completed_tool_results is not None:
            completed_index = len(completed_tool_results)
            completed_tool_results.append(
                {
                    "tool_call_id": tid,
                    "name": name,
                    "arguments": args,
                    "result": result,
                }
            )
        message_index = len(messages)
        messages.append({"role": "tool", "tool_call_id": tid, "content": result})
        if public_repo_row is not None:
            public_repo_row.update(
                {
                    "tool_call_id": tid,
                    "message_index": message_index,
                    "completed_index": completed_index,
                }
            )
            public_repo_rows.append(public_repo_row)

    if public_repo_source_items:
        from services.public_repo_tool import summarize_public_repo_read_results

        summary_result = summarize_public_repo_read_results(public_repo_source_items, focus=tool_focus)
        first_tool_call_id = str(public_repo_rows[0].get("tool_call_id") or "") if public_repo_rows else ""
        for index, row in enumerate(public_repo_rows):
            visible_data = dict(row.get("data") or {})
            visible_data["source_summary_status"] = "ok" if summary_result.get("ok") else "error"
            visible_data["source_summary_chars"] = int(summary_result.get("source_chars") or public_repo_source_chars)
            visible_data["source_summary_items"] = len(public_repo_rows)
            if tool_limit_reached:
                visible_data["tool_content_limit_reached"] = True
                visible_data["tool_content_limit_chars"] = public_repo_source_limit
                visible_data["continue_in_next_user_turn"] = True
            if summary_result.get("ok"):
                if index == 0:
                    visible_data["source_summary"] = str(summary_result.get("summary") or "")
                    visible_data["source_summary_model"] = str(summary_result.get("model") or "")
                    visible_data["source_summary_finish_reason"] = str(summary_result.get("finish_reason") or "")
                    visible_data["source_summary_output_limit_reached"] = bool(summary_result.get("output_limit_reached"))
                else:
                    visible_data["source_summary_in_tool_call_id"] = first_tool_call_id
            else:
                visible_data["ok"] = False
                visible_data["error_code"] = str(summary_result.get("error_code") or "source_summary_failed")
                visible_data["error"] = str(summary_result.get("error") or "仓库工具摘要失败")
            visible_result = json.dumps(visible_data, ensure_ascii=False)
            message_index = int(row["message_index"])
            messages[message_index]["content"] = visible_result
            completed_index = row.get("completed_index")
            if completed_tool_results is not None and isinstance(completed_index, int):
                completed_tool_results[completed_index]["result"] = visible_result
            event_ok = bool(visible_data.get("ok"))
            _emit_tool_event(
                on_tool_event,
                "tool_call_finished" if event_ok else "tool_call_failed",
                {
                    **dict(row.get("base_event") or {}),
                    "ok": event_ok,
                    "duration_ms": int((time.time() - float(row.get("started_at") or time.time())) * 1000),
                    "result_preview": _tool_event_text(visible_result),
                    "result_chars": len(visible_result),
                    **({} if event_ok else {"error": _tool_event_text(visible_data.get("error"), 500)}),
                },
            )
        public_repo_source_items.clear()
    if tool_limit_reached:
        body["tool_choice"] = "none"
    body["messages"] = messages
    return body


def collect_tool_trace_from_messages(messages: list) -> list[dict]:
    """
    从消息链提取工具调用与结果，供存档后 MiniApp 展示。
    返回项结构：{id,type,function:{name,arguments},result}
    """
    def _tool_content_to_str(msg: dict) -> str:
        c = msg.get("content")
        if isinstance(c, str):
            return c
        try:
            return json.dumps(c, ensure_ascii=False)
        except Exception:
            return str(c)

    def _following_tool_message_indices(start_idx: int) -> list[int]:
        indices: list[int] = []
        for j in range(start_idx + 1, len(messages or [])):
            mm = messages[j]
            if not isinstance(mm, dict):
                continue
            role = str(mm.get("role") or "").strip().lower()
            if role == "tool":
                indices.append(j)
                continue
            if role in {"assistant", "user"}:
                break
        return indices

    out: list[dict] = []
    used_tool_indices: set[int] = set()
    for i, m in enumerate(messages or []):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").strip().lower() != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        following_tool_indices = _following_tool_message_indices(i)
        for pos, tc in enumerate(tcs):
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            row = dict(tc)
            result_idx = None
            if tid:
                for idx in following_tool_indices:
                    if idx in used_tool_indices:
                        continue
                    tm = messages[idx]
                    if str(tm.get("tool_call_id") or "").strip() == tid:
                        result_idx = idx
                        break
            if result_idx is None:
                remaining = [idx for idx in following_tool_indices if idx not in used_tool_indices]
                if pos < len(remaining):
                    result_idx = remaining[pos]
                elif remaining:
                    result_idx = remaining[0]
            if result_idx is not None:
                used_tool_indices.add(result_idx)
                row["result"] = _tool_content_to_str(messages[result_idx])
            else:
                row["result"] = row.get("result") or ""
            out.append(row)
    return out


def sse_delta_chunk_bytes(delta_text: str) -> bytes:
    """补发一段 OpenAI 风格 SSE，仅含 delta.content（用于工具后自动附带预览链接）。"""
    payload = {
        "choices": [
            {"index": 0, "delta": {"content": delta_text}, "finish_reason": None},
        ]
    }
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


def is_sse_done_chunk(chunk: bytes) -> bool:
    if not isinstance(chunk, (bytes, bytearray)) or not bytes(chunk).startswith(b"data: "):
        return False
    return bytes(chunk)[6:].strip() == b"[DONE]"
