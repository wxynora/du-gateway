import json
import re

THINK_BLOCK_RE = re.compile(r"<(think|thinking)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)


class ReasoningStreamNormalizer:
    """Normalize one logical reasoning part across one or more stream attempts."""

    def __init__(self) -> None:
        self._text = ""
        self.start_attempt()

    @property
    def text(self) -> str:
        return self._text

    def start_attempt(self) -> None:
        self._attempt_text = ""
        self._attempt_mode = "unknown"
        self._attempt_started = False

    def feed(self, fragment: str) -> tuple[str, str] | None:
        incoming = str(fragment or "")
        if not incoming:
            return None

        if not self._attempt_started:
            candidate = incoming
            incoming_mode = "delta"
            self._attempt_started = True
        elif incoming.startswith(self._attempt_text) and len(incoming) > len(self._attempt_text):
            candidate = incoming
            incoming_mode = "snapshot"
            self._attempt_mode = "snapshot"
        elif self._attempt_mode == "snapshot" and incoming == self._attempt_text:
            candidate = incoming
            incoming_mode = "snapshot"
        else:
            candidate = self._attempt_text + incoming
            incoming_mode = "delta"
            self._attempt_mode = "delta"

        self._attempt_text = candidate
        if candidate == self._text or self._text.startswith(candidate):
            return None
        if candidate.startswith(self._text):
            suffix = candidate[len(self._text) :]
            self._text = candidate
            if incoming_mode == "snapshot":
                return "snapshot", candidate
            return ("delta", suffix) if suffix else None

        self._text = candidate
        return "snapshot", candidate

    def reconcile_snapshot(self, text: str) -> tuple[str, str] | None:
        snapshot = str(text or "")
        if not snapshot or snapshot == self._text:
            return None
        self._attempt_text = snapshot
        self._attempt_started = True
        self._attempt_mode = "snapshot"
        self._text = snapshot
        return "snapshot", snapshot


def extract_thinking_from_content(content: str) -> tuple[str, str]:
    """
    把 content 里的 <think>...</think> / <thinking>...</thinking> 块提取出来。
    返回 (stripped_content, extracted_thinking)。
    若无匹配则 extracted_thinking 为空串，content 原样返回。
    """
    if not content or not isinstance(content, str):
        return content or "", ""
    thinking_parts: list[str] = []

    def _repl(m: re.Match) -> str:
        thinking_parts.append(m.group(2).strip())
        return ""

    stripped = THINK_BLOCK_RE.sub(_repl, content).strip()
    return stripped, "\n\n".join(thinking_parts)


def normalize_reasoning_details(value) -> list:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def reasoning_text_fingerprint(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def append_unique_reasoning_text(parts: list[str], text: str) -> None:
    text = str(text or "").strip()
    key = reasoning_text_fingerprint(text)
    if not key:
        return
    for idx, existing in enumerate(parts):
        existing_key = reasoning_text_fingerprint(existing)
        if key == existing_key or key in existing_key:
            return
        if existing_key and existing_key in key:
            parts[idx] = text
            return
    parts.append(text)


def dedupe_reasoning_text_parts(parts: list[str]) -> list[str]:
    out: list[str] = []
    for part in parts or []:
        append_unique_reasoning_text(out, str(part or ""))
    return out


def extract_reasoning_text_and_details(obj: dict) -> tuple[str, list, bool]:
    reasoning_parts: list[str] = []
    details = normalize_reasoning_details(obj.get("reasoning_details")) if isinstance(obj, dict) else []
    omitted = False
    if isinstance(obj, dict):
        for rk in ("reasoning", "reasoning_content", "thinking"):
            val = obj.get(rk)
            if isinstance(val, str) and val.strip():
                reasoning_parts.append(val.strip())
        for block in obj.get("thinking_blocks") or []:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").strip()
            if btype == "thinking":
                val = block.get("thinking") or block.get("text")
                if isinstance(val, str) and val.strip():
                    reasoning_parts.append(val.strip())
            elif btype == "redacted_thinking":
                omitted = True
            details.append(block)
        content = obj.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = str(block.get("type") or "").strip()
                if btype == "thinking":
                    val = block.get("thinking") or block.get("text")
                    if isinstance(val, str) and val.strip():
                        reasoning_parts.append(val.strip())
                elif btype == "redacted_thinking":
                    omitted = True
                if btype in {"thinking", "redacted_thinking"}:
                    details.append(block)
        for item in details:
            for key in ("type", "display", "format"):
                val = str(item.get(key) or "").strip().lower()
                if val == "omitted":
                    omitted = True
            if item.get("omitted") is True:
                omitted = True
    deduped_parts = dedupe_reasoning_text_parts(reasoning_parts)
    return "\n\n".join(deduped_parts).strip(), details, omitted


def strip_thinking_from_response_json(resp_json: dict) -> dict:
    """
    从非流式上游响应中剥离 content 里的 <think> 块和结构化 reasoning 字段，
    避免 thinking 泄漏给客户端（RikkaHub / Telegram 等）。
    就地修改 resp_json 并返回；若无 choices 则原样返回。
    """
    if not isinstance(resp_json, dict):
        return resp_json
    choices = resp_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return resp_json
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return resp_json
    for key in ("reasoning", "reasoning_content", "thinking"):
        msg.pop(key, None)
    for key in ("reasoning_details", "thinking_blocks", "reasoning_omitted"):
        msg.pop(key, None)
    content = msg.get("content")
    if not isinstance(content, str):
        return resp_json
    stripped, _thinking = extract_thinking_from_content(content)
    msg["content"] = stripped
    return resp_json


def strip_reasoning_from_sse_chunk(chunk: bytes) -> bytes:
    """
    从单条 SSE chunk 中：
    1. 删除 delta 里的 reasoning/reasoning_content/thinking 字段
    2. 剥离 delta.content 里的 <think>/<thinking> 块
    避免客户端（RikkaHub 等）把思维链渲染成对话内容。
    非 data: 行或解析失败时原样返回。
    """
    if not chunk.startswith(b"data: "):
        return chunk
    payload = chunk[6:].strip()
    if payload == b"[DONE]" or not payload:
        return chunk
    try:
        j = json.loads(payload.decode("utf-8", errors="ignore"))
        delta = (j.get("choices") or [{}])[0].get("delta") if isinstance(j, dict) else None
        if not isinstance(delta, dict):
            return chunk
        changed = False
        for rk in ("reasoning", "reasoning_content", "thinking", "reasoning_details", "thinking_blocks"):
            if rk in delta:
                del delta[rk]
                changed = True
        # 剥离 delta.content 里的 <think> 块
        if isinstance(delta.get("content"), str) and THINK_BLOCK_RE.search(delta["content"]):
            stripped, _ = extract_thinking_from_content(delta["content"])
            delta["content"] = stripped
            changed = True
        if not changed:
            return chunk
        return b"data: " + json.dumps(j, ensure_ascii=False).encode("utf-8") + b"\n"
    except Exception:
        return chunk


def parse_stream_to_message(chunks: list) -> dict:
    """
    从流式 SSE chunks 解析出完整 assistant message（content + tool_calls）。
    返回 {"content": str, "tool_calls": list or None, "reasoning": str|None, ...}。
    """
    content_parts = []
    reasoning_stream = ReasoningStreamNormalizer()
    reasoning_details: list[dict] = []
    thinking_blocks: list[dict] = []
    reasoning_omitted = False
    # tool_calls 按 index 聚合，arguments 可能多 delta 拼接
    tool_calls_by_index = {}
    for chunk in chunks:
        if not chunk.startswith(b"data: "):
            continue
        payload = chunk[6:].strip()
        if payload == b"[DONE]" or not payload:
            continue
        try:
            j = json.loads(payload.decode("utf-8", errors="ignore"))
            delta = (j.get("choices") or [{}])[0].get("delta") or {}
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        if delta.get("content"):
            content_parts.append(delta["content"])
        text, details, omitted = extract_reasoning_text_and_details(delta)
        if text:
            reasoning_stream.feed(text)
        if details:
            reasoning_details.extend(details)
        for block in delta.get("thinking_blocks") or []:
            if isinstance(block, dict):
                thinking_blocks.append(block)
        if omitted:
            reasoning_omitted = True
        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index")
            if idx is None:
                continue
            if idx not in tool_calls_by_index:
                tool_calls_by_index[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            if tc.get("id"):
                tool_calls_by_index[idx]["id"] = tc["id"]
            if tc.get("type"):
                tool_calls_by_index[idx]["type"] = tc["type"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                tool_calls_by_index[idx]["function"]["name"] = fn["name"]
            if fn.get("arguments"):
                tool_calls_by_index[idx]["function"]["arguments"] += fn["arguments"]
    # 按 index 排序成列表
    sorted_tcs = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index) if tool_calls_by_index[i].get("id")]
    return {
        "content": "".join(content_parts),
        "tool_calls": sorted_tcs if sorted_tcs else None,
        "reasoning": reasoning_stream.text.strip() or None,
        "thinking_blocks": thinking_blocks or None,
        "reasoning_details": reasoning_details or None,
        "reasoning_omitted": reasoning_omitted,
    }
