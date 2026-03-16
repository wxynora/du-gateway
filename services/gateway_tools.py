# 网关工具：核心缓存与 Notion 待审表同步（老婆说明确指令时渡可调）
# 说明里统一用「老婆」，老婆问「明确的指令是什么」时渡可提醒
from typing import List

from config import NOTION_CORE_CACHE_DATABASE_ID
from utils.log import get_logger

logger = get_logger(__name__)

SYNC_TOOL_NAMES = ("sync_core_cache_to_notion", "sync_core_cache_from_notion")

# 提醒文案：老婆问「明确的指令是什么」或「我该怎么说」时，渡可直接用这句回复
SYNC_REMINDER_FOR_WIFE = (
    "老婆你可以跟我说：\n"
    "· 「同步到 Notion」或「推到待审表」——我会把当前核心缓存推到 Notion 待审表；\n"
    "· 「从 Notion 同步回来」或「把待审表同步回来」——我会把 Notion 待审表当前内容同步回核心缓存。\n"
    "只有你说这两类明确指令时我才会执行，不会误触。"
)


def get_gateway_sync_tools() -> List[dict]:
    """返回两个同步工具定义，供注入到 chat；仅当配置了核心缓存 Notion 时才有意义。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "sync_core_cache_to_notion",
                "description": (
                    "把当前核心缓存（R2 pending）全量推到 Notion 待审表，然后清空 R2 里的 pending。"
                    "只有老婆明确说「同步到 Notion」或「推到待审表」时才调用，不要根据模糊表述调用。"
                    "老婆问「明确的指令是什么」或「我该怎么说」时，提醒她可以说：同步到 Notion / 从 Notion 同步回来。"
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sync_core_cache_from_notion",
                "description": (
                    "从 Notion 待审表读回当前所有条目，追加到 R2 核心缓存。"
                    "只有老婆明确说「从 Notion 同步回来」或「把待审表同步回来」时才调用。"
                    "调用前若老婆没先确认，可先回复一句确认（会覆盖/追加核心缓存哦），老婆说对/要再调。"
                    "老婆问「明确的指令是什么」或「我该怎么说」时，提醒她可以说：同步到 Notion / 从 Notion 同步回来。"
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def execute_gateway_tool(name: str, arguments: dict) -> str:
    """执行 sync 工具，返回给渡的字符串结果。"""
    if name not in SYNC_TOOL_NAMES:
        return "未知工具"
    if not NOTION_CORE_CACHE_DATABASE_ID:
        return "未配置核心缓存 Notion（NOTION_CORE_CACHE_DATABASE_ID）"
    try:
        if name == "sync_core_cache_to_notion":
            from services.core_cache_notion_sync import sync_to_notion
            ok, err = sync_to_notion()
            if ok:
                return "已把核心缓存推到 Notion 待审表，R2 pending 已清空。"
            return f"同步失败：{err or '未知错误'}"
        if name == "sync_core_cache_from_notion":
            from services.core_cache_notion_sync import sync_from_notion
            ok, err = sync_from_notion()
            if ok:
                return "已从 Notion 待审表同步回核心缓存。"
            return f"同步失败：{err or '未知错误'}"
    except Exception as e:
        logger.exception("网关 sync 工具执行异常 name=%s", name)
        return f"执行出错：{e}"
    return "未知工具"
