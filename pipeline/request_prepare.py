import copy
import threading

from config import MAX_REQUEST_CHARS
from services import image_desc
from storage import r2_store
from utils.log import get_logger


logger = get_logger("pipeline.pipeline")


def step_clean_images_and_save_desc(body: dict, window_id: str) -> dict:
    """
    清洗层：图片进入模型前先按 Anthropic 建议压缩，并行把图片用便宜 AI 转描述存 R2。
    返回新的 body（保留可读压缩图供「发给渡」用；存 R2 时用完整清洗版，图片→描述/占位符）。
    """
    body = copy.deepcopy(body)
    skip_description_coords: set[tuple[int, int]] = set()
    for mi, msg in enumerate(body.get("messages") or []):
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for ci, part in enumerate(content):
            if isinstance(part, dict) and part.get("__skip_image_description"):
                skip_description_coords.add((mi, ci))
    body, compress_stats = image_desc.compress_images_for_anthropic(body)
    for st in compress_stats:
        if not st.get("changed"):
            continue
        logger.info(
            "图片已按 Anthropic 建议压缩 message=%s part=%s %sx%s -> %sx%s bytes=%s -> %s",
            st.get("message_index"),
            st.get("content_index"),
            st.get("width"),
            st.get("height"),
            st.get("new_width"),
            st.get("new_height"),
            st.get("bytes"),
            st.get("new_bytes"),
        )
    messages = body.get("messages") or []
    failed_skip_coords = {
        (int(st.get("message_index")), int(st.get("content_index")))
        for st in compress_stats
        if (int(st.get("message_index")), int(st.get("content_index"))) in skip_description_coords
        and str(st.get("reason") or "") in {"invalid_size", "pillow_missing", "resize_failed"}
    }
    for mi, ci in skip_description_coords:
        try:
            part = messages[mi]["content"][ci]
        except (IndexError, KeyError, TypeError):
            continue
        if not isinstance(part, dict):
            continue
        part.pop("__skip_image_description", None)
        if (mi, ci) in failed_skip_coords:
            messages[mi]["content"][ci] = {"type": "text", "text": "【图片】"}
            logger.warning("QQ 群活动图片压缩失败，已回退占位 message=%s part=%s", mi, ci)
    images = image_desc.extract_images_from_messages(messages)
    for mi, ci, b64, mime in images:
        if (mi, ci) in skip_description_coords:
            continue
        image_id = image_desc.image_description_id(b64, mime)
        msg_id = f"{window_id}_{mi}_{ci}_{image_id}"
        image_desc.mark_image_description_pending(b64, mime)
        # 异步：转描述并存 R2，不阻塞
        def _do(img_b64, mid, wid, img_mime, img_id):
            desc = None
            try:
                desc = image_desc.image_to_description(img_b64, img_mime)
            finally:
                image_desc.finish_image_description(img_b64, img_mime, desc)
            if desc:
                r2_store.save_recent_image_description(
                    wid,
                    img_id,
                    desc,
                    mime_type=img_mime,
                    message_id=mid,
                )
            else:
                logger.warning("image_desc 未生成描述 window_id=%s image_id=%s mime=%s", wid, img_id, img_mime)

        t = threading.Thread(
            target=_do,
            args=(b64, msg_id, window_id, mime, image_id),
            name=f"image-desc-{image_id}",
        )
        t.start()
    return body


def step_clean_for_forward(body: dict) -> dict:
    """
    发给当前窗口渡的清洗：只清 Rikka 预设（不替换表情包，渡按 (表情包:名字) 格式）；图片保持原样。
    两条流之一：此 body 用于转发给 AI。
    role=system 的消息（Rikkahub 设置的上下文/系统提示）不做任何清洗，原样保留。
    """
    from pipeline.cleaner import clean_message_content_for_forward

    body = copy.deepcopy(body)
    for msg in body.get("messages") or []:
        if (msg.get("role") or "").lower() == "system":
            continue  # 不清理 Rikkahub 的 system/上下文，原样保留
        c = msg.get("content")
        if c is not None:
            msg["content"] = clean_message_content_for_forward(c, msg)
    return body


def _messages_total_chars(messages: list) -> int:
    """估算 messages 总字符数（content 转为字符串长度）。"""
    total = 0
    for m in messages or []:
        c = m.get("content")
        if c is None:
            continue
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and (part.get("text") or part.get("content")):
                    total += len(str(part.get("text") or part.get("content") or ""))
                else:
                    total += len(str(part))
        else:
            total += len(str(c))
    return total


def step_trim_messages_if_over_limit(body: dict) -> dict:
    """
    当 MAX_REQUEST_CHARS > 0 且 messages 总字符数超限时，从对话中部删最老的轮次，
    保证最前面的「渡的 prompt + 所有连续 system」不被删，避免上游 input 超限导致输出被截断。
    """
    if not MAX_REQUEST_CHARS or MAX_REQUEST_CHARS <= 0:
        return body
    messages = body.get("messages") or []
    if not messages:
        return body
    total = _messages_total_chars(messages)
    if total <= MAX_REQUEST_CHARS:
        return body
    # 前段：第 0 条（渡的 prompt）+ 其后所有连续的 system
    i = 0
    while i < len(messages) and (messages[i].get("role") or "").lower() == "system":
        i += 1
    leading = messages[:i]
    conversation = messages[i:]
    if not conversation:
        return body
    leading_chars = _messages_total_chars(leading)
    if leading_chars >= MAX_REQUEST_CHARS:
        logger.warning("请求前段（渡 prompt+system）已超 MAX_REQUEST_CHARS，无法再裁对话")
        return body
    # 从 conversation 前面删，直到总长 <= 限
    body = copy.deepcopy(body)
    conv = list(conversation)
    while conv and leading_chars + _messages_total_chars(conv) > MAX_REQUEST_CHARS:
        conv.pop(0)
    dropped = len(conversation) - len(conv)
    if dropped:
        logger.info("请求超限已裁掉最老 %s 条对话，当前总字符约 %s（上限 %s）", dropped, leading_chars + _messages_total_chars(conv), MAX_REQUEST_CHARS)
    body["messages"] = leading + conv
    return body
