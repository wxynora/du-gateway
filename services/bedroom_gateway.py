# 卧室特殊通道：识别 bedroom tag 后，原文照常存 R2；不写动态层/核心缓存；额外写 Notion 卧室房间
from utils.time_aware import now_beijing_iso

from config import NOTION_BEDROOM_PAGE_ID
from services import notion_client
from utils.log import get_logger

logger = get_logger(__name__)

_NOTION_RICH_TEXT_MAX = 2000


def append_bedroom_raw(window_id: str, round_index: int, raw_text: str) -> None:
    """
    追加卧室原文到 Notion（页面块子级）。
    event_id 用 window_id + round_index，写入正文里便于肉眼查重；不做查重、不改原文。
    """
    if not NOTION_BEDROOM_PAGE_ID:
        logger.debug("NOTION_BEDROOM_PAGE_ID 未配置，跳过卧室 Notion 写入")
        return
    if not raw_text:
        return

    event_id = f"{window_id}-{round_index}"
    ts = now_beijing_iso()
    header = f"[event_id:{event_id}] [{ts}]"
    text = f"{header}\n{raw_text}".strip()

    children = []
    while text:
        chunk = text[:_NOTION_RICH_TEXT_MAX]
        text = text[_NOTION_RICH_TEXT_MAX:]
        children.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
            }
        )
    _, err = notion_client.append_block_children(NOTION_BEDROOM_PAGE_ID, children)
    if err:
        logger.error("卧室 Notion 写入失败 page_id=%s error=%s，重试一次", NOTION_BEDROOM_PAGE_ID, err)
        _, err = notion_client.append_block_children(NOTION_BEDROOM_PAGE_ID, children)
    if err:
        logger.error("卧室 Notion 再次失败 page_id=%s error=%s", NOTION_BEDROOM_PAGE_ID, err)

