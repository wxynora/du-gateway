import copy
import threading

from pipeline.pipeline import step_run_post_archive_tasks
from utils.log import get_logger

logger = get_logger(__name__)


def run_nonstream_post_archive_in_background(
    *,
    window_id: str,
    round_index: int,
    round_messages: list,
    reply_channel: str = "",
    skip_dynamic_layer: bool = False,
) -> None:
    """非流式入口已同步写入 R2 后，只把总结/动态层等慢任务放后台。"""

    def _runner():
        try:
            step_run_post_archive_tasks(
                window_id,
                round_index,
                round_messages,
                skip_dynamic_layer=skip_dynamic_layer,
            )
            logger.info(
                "非流式后台慢任务完成 window_id=%s channel=%s round_index=%s skip_dynamic_layer=%s",
                window_id,
                reply_channel,
                round_index,
                skip_dynamic_layer,
            )
        except Exception:
            logger.warning(
                "非流式后台慢任务失败 window_id=%s channel=%s round_index=%s",
                window_id,
                reply_channel,
                round_index,
                exc_info=True,
            )

    threading.Thread(target=_runner, name=f"nonstream-post-archive-{window_id}", daemon=True).start()


def strip_co_read_section_raw_text_for_archive(msg: dict) -> dict:
    def _strip_text(text: str) -> str:
        raw = str(text or "")
        start_marker = "[CO-READ SECTION]"
        end_marker = "[/CO-READ SECTION]"
        raw_marker = "本小节原文："
        next_marker = "辛玥的粉色标记："
        if start_marker not in raw or raw_marker not in raw:
            return raw
        out = []
        pos = 0
        while True:
            start = raw.find(start_marker, pos)
            if start < 0:
                out.append(raw[pos:])
                break
            end = raw.find(end_marker, start)
            if end < 0:
                out.append(raw[pos:])
                break
            block_end = end + len(end_marker)
            block = raw[start:block_end]
            raw_idx = block.find(raw_marker)
            next_idx = block.find(next_marker, raw_idx + len(raw_marker)) if raw_idx >= 0 else -1
            if raw_idx >= 0 and next_idx >= 0:
                block = (
                    block[:raw_idx]
                    + "本小节原文：\n（已从会话存档删除；原书正文仅保留在 co_read/books）\n\n"
                    + block[next_idx:]
                )
            out.append(raw[pos:start])
            out.append(block)
            pos = block_end
        return "".join(out)

    clean = copy.deepcopy(msg or {})
    content = clean.get("content")
    if isinstance(content, str):
        clean["content"] = _strip_text(content)
    elif isinstance(content, list):
        next_content = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                next_content.append({**part, "text": _strip_text(str(part.get("text") or ""))})
            else:
                next_content.append(part)
        clean["content"] = next_content
    return clean


def strip_qq_group_context_for_archive(msg: dict, window_id: str = "") -> dict:
    return compact_qq_group_context_for_archive(msg, window_id=window_id)


def _message_text_for_archive(msg: dict) -> str:
    content = (msg or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                parts.append(str(part.get("text") or ""))
        return "\n".join(parts)
    return str(content or "")


def _normalize_qq_group_line(line: str) -> str:
    return " ".join(str(line or "").strip().split())


_QQ_GROUP_ARCHIVE_META_PREFIXES = (
    "群号：",
    "当前发言人：",
    "身份标记：",
    "本次新增群聊上下文：",
    "当前 @ 你的消息：",
)


def _qq_group_seen_lines_from_rounds(window_id: str, last_n: int = 8) -> set[str]:
    if not window_id:
        return set()
    try:
        from storage import r2_store

        rounds = r2_store.get_conversation_rounds(window_id, last_n=last_n) or []
    except Exception:
        return set()

    seen: set[str] = set()
    for item in rounds:
        if not isinstance(item, dict):
            continue
        for message in item.get("messages") or []:
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "").strip().lower() != "user":
                continue
            text = _message_text_for_archive(message)
            if "【QQ 群聊" not in text:
                continue
            for raw_line in text.splitlines():
                line = _normalize_qq_group_line(raw_line)
                if not line or "：" not in line:
                    continue
                if line.startswith(_QQ_GROUP_ARCHIVE_META_PREFIXES):
                    continue
                seen.add(line)
    return seen


def compact_qq_group_context_for_archive(msg: dict, window_id: str = "") -> dict:
    def _strip_text(text: str) -> str:
        raw = str(text or "")
        marker = "当前 @ 你的消息："
        if "【QQ 群聊】" not in raw or marker not in raw:
            return raw
        before, current = raw.split(marker, 1)
        current = current.strip()
        if not current:
            current = "（只 @ 了你，没有附加文字）"

        seen_lines = _qq_group_seen_lines_from_rounds(window_id)
        context_lines = []
        context_marker = "你只有在被 @ 时才回复。下面是本次 @ 前的最近群聊消息，用作公开上下文："
        if context_marker in before:
            context_raw = before.split(context_marker, 1)[1]
            for raw_line in context_raw.splitlines():
                line = _normalize_qq_group_line(raw_line)
                if not line or line.startswith("（") or "：" not in line:
                    continue
                if line in seen_lines:
                    continue
                seen_lines.add(line)
                context_lines.append(str(raw_line or "").strip())

        meta_lines = []
        for raw_line in before.splitlines():
            line = str(raw_line or "").strip()
            if line.startswith(("群号：", "当前发言人：", "身份标记：")):
                meta_lines.append(line)
        parts = ["【QQ 群聊 @】", *meta_lines]
        if context_lines:
            parts.extend(["本次新增群聊上下文：", *context_lines])
        else:
            parts.extend(["本次新增群聊上下文：", "（与最近存档重复，已省略）"])
        parts.extend([marker, current])
        return "\n".join(parts)

    clean = copy.deepcopy(msg or {})
    content = clean.get("content")
    if isinstance(content, str):
        clean["content"] = _strip_text(content)
    elif isinstance(content, list):
        next_content = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                next_content.append({**part, "text": _strip_text(str(part.get("text") or ""))})
            else:
                next_content.append(part)
        clean["content"] = next_content
    return clean


def strip_wenyou_ai_player_context_for_archive(msg: dict) -> dict:
    def _strip_text(text: str) -> str:
        raw = str(text or "")
        start_marker = "[WENYOU AI PLAYER TURN]"
        end_marker = "[/WENYOU AI PLAYER TURN]"
        context_marker = "只读上下文 JSON："
        action_marker = "辛玥本轮行动："
        if start_marker not in raw or context_marker not in raw:
            return raw
        out = []
        pos = 0
        while True:
            start = raw.find(start_marker, pos)
            if start < 0:
                out.append(raw[pos:])
                break
            end = raw.find(end_marker, start)
            if end < 0:
                out.append(raw[pos:])
                break
            block_end = end + len(end_marker)
            block = raw[start:block_end]
            context_idx = block.find(context_marker)
            action_idx = block.find(action_marker, context_idx + len(context_marker)) if context_idx >= 0 else -1
            if context_idx >= 0 and action_idx >= 0:
                block = (
                    block[:context_idx]
                    + "只读上下文 JSON：\n（已从会话存档删除；文游状态保留在 wenyou/session 与 wallet 中）\n\n"
                    + block[action_idx:]
                )
            out.append(raw[pos:start])
            out.append(block)
            pos = block_end
        return "".join(out)

    clean = copy.deepcopy(msg or {})
    content = clean.get("content")
    if isinstance(content, str):
        clean["content"] = _strip_text(content)
    elif isinstance(content, list):
        next_content = []
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                next_content.append({**part, "text": _strip_text(str(part.get("text") or ""))})
            else:
                next_content.append(part)
        clean["content"] = next_content
    return clean
