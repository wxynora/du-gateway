from __future__ import annotations

import json
import re
from typing import Any

from services.reasoning_utils import extract_reasoning_text_and_details
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

MARKER_START = "<DU_INNER_OS>"
MARKER_END = "</DU_INNER_OS>"

PSEUDO_COT_DYNAMIC_SYSTEM = f"""在回复小玥前必须先输出：
{MARKER_START}
脑内 OS：内心独白。
……
{MARKER_END}"""

_REFUSAL_WORDS = (
    "sorry",
    "can't",
    "cannot",
    "unable",
    "won't",
    "refuse",
    "无法",
    "不能",
    "不便",
    "拒绝",
)
_SENSITIVE_WORDS = (
    "sexual",
    "sexually",
    "explicit",
    "erotic",
    "nsfw",
    "色情",
    "性内容",
    "露骨",
)


def pseudo_cot_instruction_enabled(body: dict) -> bool:
    if not isinstance(body, dict):
        return False
    for msg in body.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").strip().lower() != "system":
            continue
        if MARKER_START in str(msg.get("content") or ""):
            return True
    return False


def split_inner_os_from_text(full_text: str) -> tuple[str, str]:
    if not full_text or not isinstance(full_text, str):
        return full_text or "", ""
    start = full_text.find(MARKER_START)
    if start < 0:
        return full_text, ""
    end = full_text.find(MARKER_END, start + len(MARKER_START))
    if end < 0:
        return full_text[:start].rstrip(), ""
    inner = full_text[start + len(MARKER_START) : end].strip()
    visible = full_text[:start] + full_text[end + len(MARKER_END) :]
    if not full_text[:start].strip():
        visible = visible.lstrip()
    return visible.strip(), inner


def extract_inner_os_from_response_json(resp_json: dict) -> tuple[dict, str]:
    if not isinstance(resp_json, dict):
        return resp_json, ""
    choices = resp_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return resp_json, ""
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return resp_json, ""
    content = msg.get("content")
    if isinstance(content, str):
        visible, inner_os = split_inner_os_from_text(content)
        if inner_os or visible != content:
            msg["content"] = visible
        return resp_json, inner_os
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and str(item.get("type") or "") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        if not parts:
            return resp_json, ""
        merged = "".join(parts)
        visible, inner_os = split_inner_os_from_text(merged)
        if inner_os or visible != merged:
            msg["content"] = visible
        return resp_json, inner_os
    return resp_json, ""


def _maybe_waiting_for_start_marker(text: str) -> bool:
    stripped = str(text or "").lstrip()
    if not stripped:
        return True
    if len(stripped) >= len(MARKER_START):
        return False
    return MARKER_START.startswith(stripped)


def compute_visible_streaming(acc: str) -> str:
    if not acc:
        return ""
    start = acc.find(MARKER_START)
    if start < 0:
        return "" if _maybe_waiting_for_start_marker(acc) else acc
    end = acc.find(MARKER_END, start + len(MARKER_START))
    if end < 0:
        return acc[:start].rstrip()
    visible = acc[:start] + acc[end + len(MARKER_END) :]
    if not acc[:start].strip():
        visible = visible.lstrip()
    return visible


class PseudoCotStreamState:
    def __init__(self) -> None:
        self.acc = ""
        self._last_visible_len = 0

    def feed_delta(self, delta_piece: str) -> str:
        self.acc += str(delta_piece or "")
        visible = compute_visible_streaming(self.acc)
        out = visible[self._last_visible_len :]
        self._last_visible_len = len(visible)
        return out


def transform_sse_chunk_bytes(chunk: bytes, state: PseudoCotStreamState) -> bytes:
    try:
        text = chunk.decode("utf-8")
    except Exception:
        return chunk
    lines = text.split("\n")
    out_lines: list[str] = []
    for line in lines:
        if line.startswith("data: ") and line[6:].strip() != "[DONE]":
            try:
                payload = json.loads(line[6:])
                ch0 = (payload.get("choices") or [{}])[0]
                delta = ch0.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str):
                    delta["content"] = state.feed_delta(content)
                    ch0["delta"] = delta
                    payload["choices"][0] = ch0
                    out_lines.append("data: " + json.dumps(payload, ensure_ascii=False))
                else:
                    out_lines.append(line)
            except (json.JSONDecodeError, KeyError, TypeError, IndexError):
                out_lines.append(line)
        else:
            out_lines.append(line)
    return "\n".join(out_lines).encode("utf-8")


def is_reasoning_summary_refusal(reasoning_text: str = "", details: Any = None) -> bool:
    parts = [str(reasoning_text or "")]
    if details:
        try:
            parts.append(json.dumps(details, ensure_ascii=False, default=str))
        except Exception:
            parts.append(str(details))
    haystack = "\n".join(parts).strip().lower()
    if not haystack:
        return False
    has_refusal = any(word in haystack for word in _REFUSAL_WORDS)
    has_sensitive = any(word in haystack for word in _SENSITIVE_WORDS)
    if re.search(r"(can't|cannot|unable to|won't|无法|不能|不便|拒绝).{0,80}(rewrite|转写|改写)", haystack):
        return True
    if re.search(r"(rewrite|转写|改写).{0,80}(can't|cannot|unable to|won't|无法|不能|不便|拒绝)", haystack):
        return True
    if has_refusal and has_sensitive:
        return True
    if "contains sexual" in haystack or "content contains sexual" in haystack:
        return True
    return False


def apply_pseudo_cot_state_and_fallback(window_id: str, msg: dict, inner_os: str = "") -> dict:
    if not isinstance(msg, dict):
        return msg
    official_text, details, omitted = extract_reasoning_text_and_details(msg)
    refused = is_reasoning_summary_refusal(official_text, details)
    now = now_beijing_iso()
    if refused:
        try:
            r2_store.save_pseudo_cot_state(
                window_id,
                {
                    "enabled": True,
                    "reason": "official_summary_refused",
                    "last_refusal_at": now,
                    "updated_at": now,
                },
            )
        except Exception as e:
            logger.warning("pseudo_cot_state enable failed window_id=%s error=%s", window_id, e)
        inner = str(inner_os or "").strip()
        if inner:
            msg["reasoning"] = inner
            msg["reasoning_source"] = "du_inner_os_fallback"
            msg["official_reasoning_refused"] = True
            msg["official_reasoning_refusal_text"] = official_text[:1000]
            if omitted:
                msg["reasoning_omitted"] = True
        return msg
    try:
        state = r2_store.get_pseudo_cot_state(window_id)
        if isinstance(state, dict) and state.get("enabled"):
            r2_store.save_pseudo_cot_state(
                window_id,
                {
                    **state,
                    "enabled": False,
                    "closed_at": now,
                    "closed_reason": "official_summary_not_refused",
                    "updated_at": now,
                },
            )
    except Exception as e:
        logger.warning("pseudo_cot_state disable failed window_id=%s error=%s", window_id, e)
    return msg
