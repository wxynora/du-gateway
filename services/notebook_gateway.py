# 小本本：网关提前拎出、打时间戳、存 R2（按时间排序）+ Notion 双存，不动原文
# 触发条件：消息里同时含有「笔记本 emoji」和「小本本更新」才截取（从「小本本更新」到句尾）
from utils.time_aware import now_beijing_iso
from typing import Any

from config import NOTION_NOTEBOOK_PAGE_ID

# 📝 + 「小本本更新」才触发截取，避免误触
NOTEBOOK_EMOJI = "\U0001F4DD"  # 📝
NOTEBOOK_PHRASE = "小本本更新"
from storage import r2_store
from services import notion_client
from utils.log import get_logger

logger = get_logger(__name__)

# Notion 单段 rich_text 约 2000 字符限制，长文拆成多段
_NOTION_RICH_TEXT_MAX = 2000


def _content_to_str(content: Any) -> str:
    """把 message content（str 或 list of parts）转成纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                else:
                    parts.append(f"[{c.get('type', '')}]")
            else:
                parts.append(str(c))
        return " ".join(parts).strip()
    return str(content).strip()


def _has_notebook_emoji(text: str) -> bool:
    """消息里是否含有 📝。"""
    if not text:
        return False
    for c in text:
        if c in NOTEBOOK_EMOJI:
            return True
    return False


def extract_entries_from_round(round_messages: list) -> list[str]:
    """
    从本轮对话中识别「小本本」内容并拎出原文（不删改）。
    仅当消息同时含有「笔记本 emoji」和「小本本更新」时，才从「小本本更新」截取到该条消息结尾写入。
    可能返回 0/1/2 条。
    """
    if not round_messages:
        return []
    entries = []
    for m in round_messages:
        raw = m.get("content")
        text = _content_to_str(raw)
        if not text or NOTEBOOK_PHRASE not in text:
            continue
        if not _has_notebook_emoji(text):
            continue
        start_idx = text.find(NOTEBOOK_PHRASE)
        snippet = text[start_idx:].strip()
        if snippet:
            entries.append(snippet)
    return entries


def save_entry(content: str) -> None:
    """
    将一条小本本写入 R2（带时间戳、按时间排序）并追加到 Notion 页面。
    原文不动，仅加时间戳。
    """
    content = (content or "").strip()
    if not content:
        return
    ts = now_beijing_iso()
    # R2（失败打 error 并重试一次）
    ok = r2_store.notebook_append_entry(content)
    if not ok:
        logger.error("小本本写 R2 失败，重试一次")
        ok = r2_store.notebook_append_entry(content)
    if not ok:
        logger.error("小本本写 R2 再次失败，仍尝试写 Notion")
    # Notion：追加一段 [时间] 原文（失败打 error 并重试一次）
    if NOTION_NOTEBOOK_PAGE_ID:
        line = f"[{ts}] {content}"
        children = []
        while line:
            chunk = line[:_NOTION_RICH_TEXT_MAX]
            line = line[_NOTION_RICH_TEXT_MAX:]
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                },
            })
        _, err = notion_client.append_block_children(NOTION_NOTEBOOK_PAGE_ID, children)
        if err:
            logger.error("小本本写 Notion 失败 page_id=%s error=%s，重试一次", NOTION_NOTEBOOK_PAGE_ID, err)
            _, err = notion_client.append_block_children(NOTION_NOTEBOOK_PAGE_ID, children)
        if err:
            logger.error("小本本写 Notion 再次失败 page_id=%s error=%s", NOTION_NOTEBOOK_PAGE_ID, err)
    else:
        logger.debug("NOTION_NOTEBOOK_PAGE_ID 未配置，跳过 Notion 小本本写入")
