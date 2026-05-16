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
) -> None:
    """非流式入口已同步写入 R2 后，只把总结/动态层等慢任务放后台。"""

    def _runner():
        try:
            step_run_post_archive_tasks(window_id, round_index, round_messages)
            logger.info("非流式后台慢任务完成 window_id=%s channel=%s round_index=%s", window_id, reply_channel, round_index)
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
