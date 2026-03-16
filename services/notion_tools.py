# 渡通过工具调用 Notion API：检索与写入（NOTION_TOOLS_ENABLED=1 时注入到对话）
import json
from typing import Any, List

from config import (
    NOTION_CORE_CACHE_DATABASE_ID,
    NOTION_NOTEBOOK_DATABASE_ID,
    NOTION_NOTEBOOK_PAGE_ID,
    NOTION_TOOLS_ENABLED,
)
from services import notion_client
from utils.log import get_logger
from utils.time_aware import iso_to_display_time, now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)


def _note_time_to_iso(note_time: str | None) -> str:
    """把渡传的 note_time（ISO 或 YYYY-MM-DD）转成北京时间的 ISO 字符串供 Notion；无效或空则用当前时间。"""
    if not note_time or not isinstance(note_time, str):
        return now_beijing_iso()
    dt = parse_iso_to_beijing(note_time.strip())
    if dt is None:
        return now_beijing_iso()
    return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

NOTION_RICH_TEXT_MAX = 2000
# Notion 标题/单段内容上限，严格 ≤2000 避免 400；留余量防编码计数差异
NOTION_TITLE_MAX = 1990
# 小本本 Database 模式下的属性名（需与 Notion 里建的列名一致）
NOTEBOOK_DB_PROP_CONTENT = "内容"
NOTEBOOK_DB_PROP_TIME = "时间"


def write_notebook_entry_to_database(content: str, note_time: str | None = None) -> tuple[bool, str]:
    """
    往小本本 Database 写一条（归档脚本用）。content 为截取的小本本正文，note_time 为该条自己的时间（如 2025-03-11T07:00:00）。
    返回 (成功, 错误信息)。
    """
    content = (content or "").strip()
    if not content:
        return False, "content 为空"
    if not NOTION_NOTEBOOK_DATABASE_ID:
        return False, "未配置 NOTION_NOTEBOOK_DATABASE_ID"
    iso_time = _note_time_to_iso(note_time)
    display_time = iso_to_display_time(iso_time) or iso_time  # 给人看：2026年03月07日 14:41
    title_content = content[:NOTION_TITLE_MAX]
    props = {
        NOTEBOOK_DB_PROP_CONTENT: {"title": [{"text": {"content": title_content}}]},
        NOTEBOOK_DB_PROP_TIME: {"rich_text": [{"type": "text", "text": {"content": display_time}}]},
    }
    _, err = notion_client.create_page(
        parent={"database_id": NOTION_NOTEBOOK_DATABASE_ID},
        properties=props,
    )
    if err:
        logger.warning("小本本 Database 写入失败 err=%s", err)
        return False, str(err)
    return True, ""


def get_notion_tools_for_inject() -> List[dict]:
    """返回要注入到 chat 的 tools 列表（未配置小本本则不包含 notion_append_to_notebook）。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "notion_search",
                "description": "在 Notion 中按关键词检索页面/数据库，返回匹配条目的标题与链接。需要查 Notion 里有什么内容时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词，如「小本本」「日记」「会议」"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "notion_append_to_page",
                "description": "向指定 Notion 页面追加一段内容（段落块，带时间戳）。用于写日记、记笔记等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string", "description": "Notion 页面 ID（32 位十六进制，可从页面 URL 取）"},
                        "content": {"type": "string", "description": "要追加的正文内容"},
                    },
                    "required": ["page_id", "content"],
                },
            },
        },
    ]
    if NOTION_NOTEBOOK_DATABASE_ID or NOTION_NOTEBOOK_PAGE_ID:
        params = {
            "content": {"type": "string", "description": "要记下的内容"},
            "note_time": {
                "type": "string",
                "description": "这条记录所指的时间（用于排序），ISO 或 YYYY-MM-DD，如 2025-03-11 或 2025-03-11T14:30:00。不传则用当前时间。",
            },
        }
        desc = "向网关配置的「小本本」记一条。若小本本是数据库则按 note_time 排序（最新在上）；不传 note_time 用当前时间。"
        tools.append({
            "type": "function",
            "function": {
                "name": "notion_append_to_notebook",
                "description": desc,
                "parameters": {"type": "object", "properties": params, "required": ["content"]},
            },
        })
    if NOTION_CORE_CACHE_DATABASE_ID:
        from services.gateway_tools import get_gateway_sync_tools
        tools.extend(get_gateway_sync_tools())
    from services.weather_almanac import get_weather_almanac_tools
    tools.extend(get_weather_almanac_tools())
    return tools


def _append_content_to_page(page_id: str, content: str, add_timestamp: bool = True) -> tuple[bool, str]:
    """向 Notion 页面追加一段内容，返回 (成功, 说明)。"""
    if not page_id or not content or not content.strip():
        return False, "page_id 或 content 为空"
    ts = now_beijing_iso()
    line = f"[{ts}] {content.strip()}" if add_timestamp else content.strip()
    children = []
    rest = line
    while rest:
        chunk = rest[:NOTION_RICH_TEXT_MAX]
        rest = rest[NOTION_RICH_TEXT_MAX:]
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        })
    _, err = notion_client.append_block_children(page_id, children)
    if err:
        logger.warning("Notion append 失败 page_id=%s err=%s", page_id[:8], err)
        return False, str(err)
    return True, "已追加"


def execute_tool(name: str, arguments: dict) -> str:
    """执行单个工具（Notion、网关 sync、天气、黄历），返回给模型的字符串结果。"""
    from services.gateway_tools import SYNC_TOOL_NAMES, execute_gateway_tool
    if name in SYNC_TOOL_NAMES:
        return execute_gateway_tool(name, arguments)
    if name in ("get_weather", "get_almanac"):
        from services.weather_almanac import execute_weather_almanac_tool
        return execute_weather_almanac_tool(name, arguments)
    try:
        if name == "notion_search":
            query = (arguments.get("query") or "").strip()
            if not query:
                return "query 不能为空"
            data, err = notion_client.search(query=query)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            if not data or not isinstance(data.get("results"), list):
                return "未返回结果"
            results = data.get("results", [])[:10]
            lines = []
            for item in results:
                title = ""
                props = item.get("properties") or {}
                for pid, prop in props.items():
                    if not isinstance(prop, dict):
                        continue
                    if "title" in prop and isinstance(prop["title"], list):
                        title = " ".join(
                            t.get("plain_text", "") for t in prop["title"] if isinstance(t, dict)
                        ).strip()
                        break
                url = (item.get("url") or "").strip()
                lines.append(f"- {title or '(无标题)'} {url}")
            return "\n".join(lines) if lines else "无匹配页面"

        if name == "notion_append_to_page":
            page_id = (arguments.get("page_id") or "").strip().replace("-", "")
            content = (arguments.get("content") or "").strip()
            ok, msg = _append_content_to_page(page_id, content)
            return msg

        if name == "notion_append_to_notebook":
            content = (arguments.get("content") or "").strip()
            if not content:
                return "content 为空"
            note_time_str = (arguments.get("note_time") or "").strip() or None
            iso_time = _note_time_to_iso(note_time_str)

            if NOTION_NOTEBOOK_DATABASE_ID:
                # Database 模式：新建一行，属性「内容」+「时间」（给人看格式），Notion 里按时间降序=最新在上
                display_time = iso_to_display_time(iso_time) or iso_time
                title_content = content[:NOTION_TITLE_MAX]
                props = {
                    NOTEBOOK_DB_PROP_CONTENT: {"title": [{"text": {"content": title_content}}]},
                    NOTEBOOK_DB_PROP_TIME: {"rich_text": [{"type": "text", "text": {"content": display_time}}]},
                }
                _, err = notion_client.create_page(
                    parent={"database_id": NOTION_NOTEBOOK_DATABASE_ID},
                    properties=props,
                )
                if err:
                    logger.warning("小本本 Database 写入失败 err=%s", err)
                    return str(err)
                return "已记入小本本（按时间排序，最新在上）"
            if NOTION_NOTEBOOK_PAGE_ID:
                # 页面模式：往页面追加块，时间用给人看格式
                display_time = iso_to_display_time(iso_time) or iso_time
                line = f"[{display_time}] {content}"
                children = []
                rest = line
                while rest:
                    chunk = rest[:NOTION_RICH_TEXT_MAX]
                    rest = rest[NOTION_RICH_TEXT_MAX:]
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
                    })
                _, err = notion_client.append_block_children(NOTION_NOTEBOOK_PAGE_ID, children)
                if err:
                    logger.warning("小本本 Page 写入失败 err=%s", err)
                    return str(err)
                return "已追加到小本本"
            return "未配置小本本（NOTION_NOTEBOOK_DATABASE_ID 或 NOTION_NOTEBOOK_PAGE_ID）"

        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.exception("Notion 工具执行异常 name=%s", name)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
