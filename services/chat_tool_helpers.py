import copy
import json
import re

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
    "如果已经够了，直接给最终答复。"
)
_TOOL_EMPTY_FINAL_RETRY_INSTRUCTION = (
    "前面的工具已经执行过了。\n"
    "如果还需要信息，直接继续调用工具；如果已经够了，必须直接给用户一条可见的最终回复。\n"
    "不要返回空 content，不要只给 reasoning / thinking。"
)


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
    messages.insert(insert_idx, {"role": "system", "content": instruction})
    body["messages"] = messages
    return body


def inject_tool_midstream_retry_instruction(body: dict) -> dict:
    return inject_tool_retry_instruction(body, _TOOL_MIDSTREAM_RETRY_INSTRUCTION)


def inject_tool_empty_final_retry_instruction(body: dict) -> dict:
    return inject_tool_retry_instruction(body, _TOOL_EMPTY_FINAL_RETRY_INSTRUCTION)


def append_tool_results_and_continue(body: dict, assistant_message: dict, tool_calls: list, execute_tool) -> dict:
    """执行 tool_calls，将 assistant 消息与各 tool 结果追加到 body["messages"]，返回新 body 供继续请求。"""
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
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
        try:
            result = execute_tool(name, args)
        except Exception as _tool_exc:
            logger.warning("execute_tool 异常 name=%s error=%s", name, _tool_exc)
            result = json.dumps({"ok": False, "error": f"工具执行异常: {_tool_exc}"}, ensure_ascii=False)
        messages.append({"role": "tool", "tool_call_id": tid, "content": result})
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
                row["result"] = ""
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
