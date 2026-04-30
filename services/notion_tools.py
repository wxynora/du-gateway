# 渡通过工具调用 Notion API：检索、读正文、待审表编辑、交换日记、日程本（NOTION_TOOLS_ENABLED=1）
import json
from typing import Any, Dict, FrozenSet, List, Optional, Set

# 关键词触发的扩展工具分组（不常驻，按用户消息关键词决定是否注入）
NOTION_EXTENDED_GROUPS: Dict[str, Dict] = {
    "schedule": {
        "keywords": ("日程", "待办", "约会", "纪念日", "schedule", "安排", "行程"),
        "names": frozenset({"notion_schedule_list", "notion_schedule_create", "notion_schedule_update"}),
    },
    "sync": {
        "keywords": ("同步", "待审表", "推到notion", "推到 notion", "同步回", "待审"),
        "names": frozenset({"sync_core_cache_to_notion", "sync_core_cache_from_notion"}),
    },
    "notion_read": {
        "keywords": ("搜索", "检索", "查一下", "找一下", "notion里", "notion 里", "页面", "正文", "read_page", "追加到"),
        "names": frozenset({"notion_search", "notion_read_page_body", "notion_append_to_page"}),
    },
    "core_cache": {
        "keywords": ("核心缓存", "缓存层", "整理缓存", "缓存表", "core cache"),
        "names": frozenset({"notion_core_cache_list", "notion_core_cache_update"}),
    },
}

# 所有扩展工具名（用于在 expanded 逻辑里快速判断）
_ALL_EXTENDED_NAMES: FrozenSet[str] = frozenset(
    name for g in NOTION_EXTENDED_GROUPS.values() for name in g["names"]
)

from config import (
    NOTION_CORE_CACHE_DATABASE_ID,
    NOTION_EXCHANGE_DIARY_DATABASE_ID,
    NOTION_NOTEBOOK_DATABASE_ID,
    NOTION_NOTEBOOK_PAGE_ID,
    NOTION_SCHEDULE_DATABASE_ID,
    NOTION_TOOLS_ENABLED,
)
from services import notion_client
from services.mcp_forum_tools import execute_forum_tool
from utils.log import get_logger
from utils.time_aware import iso_to_display_time, now_beijing_iso, parse_iso_to_beijing, today_beijing

logger = get_logger(__name__)


def _normalize_note_write_content(raw: str) -> str:
    """
    规整 note_write 内容，避免把「渡的记事本」整段历史再次写成新条目。
    规则：
    1) 去掉标题/包裹标记（如【渡的记事本】）。
    2) 按行拆分后优先取“新增且非重复”的短句。
    3) 若无法判定，回退原文本（不做激进改写）。
    """
    text = str(raw or "").replace("\r", "").strip()
    if not text:
        return ""
    lines = [x.strip() for x in text.split("\n") if x.strip()]
    if not lines:
        return text
    # 去掉明显标题行
    cleaned: list[str] = []
    for ln in lines:
        if ln.startswith("【") and ln.endswith("】"):
            continue
        if ln in ("渡的记事本", "以上为固定记事本"):
            continue
        if ln.startswith("- "):
            ln = ln[2:].strip()
        if ln:
            cleaned.append(ln)
    if not cleaned:
        return text
    try:
        from storage import r2_store
        existing = {str((x or {}).get("content") or "").strip() for x in (r2_store.get_du_notebook_entries() or [])}
    except Exception:
        existing = set()
    # 倒序挑第一条“不是历史重复内容”的行（通常新内容在末尾）
    for ln in reversed(cleaned):
        if ln and ln not in existing:
            return ln
    # 都是重复内容时，取最后一行，至少不把整段旧内容再塞一遍
    return cleaned[-1]


def _extract_first_nonempty_prop(page: dict, name_to_id: dict, candidates: list[str], prop_type: str) -> str:
    """按候选列名顺序取第一个非空属性值。"""
    for name in candidates:
        pid = (name_to_id or {}).get(name)
        if not pid:
            continue
        val = _extract_prop_from_page(page, pid, prop_type)
        if val is None:
            continue
        s = str(val).strip()
        if s:
            return s
    return ""


def _collect_rich_text_props_as_body(page: dict) -> str:
    """把页面所有 rich_text 列拼成正文兜底（用于数据库条目无 block 正文时）。"""
    props = (page or {}).get("properties") or {}
    parts: list[str] = []
    for prop in props.values():
        if not isinstance(prop, dict):
            continue
        if (prop.get("type") or "").strip() != "rich_text":
            continue
        arr = prop.get("rich_text") or []
        text = " ".join(t.get("plain_text", "") for t in arr if isinstance(t, dict)).strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _extract_prop_from_page(page: dict, prop_id: str, prop_type: str) -> Any:
    """从页面 properties 按 id 和类型取值。"""
    p = (page.get("properties") or {}).get(prop_id)
    if not p:
        return None
    if prop_type == "title":
        return " ".join(t.get("plain_text", "") for t in (p.get("title") or []) if isinstance(t, dict)).strip()
    if prop_type == "rich_text":
        return " ".join(t.get("plain_text", "") for t in (p.get("rich_text") or []) if isinstance(t, dict)).strip()
    if prop_type == "select":
        s = p.get("select")
        return s.get("name") if s else None
    if prop_type == "number":
        return p.get("number")
    if prop_type == "date":
        d = p.get("date")
        return d.get("start") if d else None
    if prop_type == "checkbox":
        return p.get("checkbox")
    if prop_type == "created_time":
        return p.get("created_time")
    return None


def _prop_title(val: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": (val or "")[:NOTION_TITLE_MAX]}}]}


def _prop_rich(val: str) -> dict:
    if not val:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": (val or "")[:NOTION_RICH_TEXT_MAX]}}]}


def _prop_select(val: str) -> dict:
    return {"select": {"name": (val or "").strip()} if (val or "").strip() else None}


def _prop_number(val: Optional[int]) -> dict:
    return {"number": val if val is not None else 0}


def _prop_date(iso_str: Optional[str]) -> dict:
    if not iso_str:
        return {"date": None}
    return {"date": {"start": iso_str.strip()[:50]}}


def _prop_checkbox(val: bool) -> dict:
    return {"checkbox": bool(val)}


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


def get_notion_tools_for_inject(mode: str = "expanded", active_groups: Optional[Set[str]] = None) -> List[dict]:
    """返回要注入到 chat 的 tools 列表。mode=daily|expanded。"""
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
                "name": "notion_read_page_body",
                "description": "读取指定 Notion 页面的标题和正文内容（块文本）。用于查看某页的完整内容。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string", "description": "Notion 页面 ID（32 位十六进制，可从链接或 notion_search 得到）"},
                    },
                    "required": ["page_id"],
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
    if NOTION_CORE_CACHE_DATABASE_ID:
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "notion_core_cache_list",
                    "description": "列出核心缓存待审表当前条目（id、content、tag、importance、mention_count、promoted_at、page_id）。用于查看待审内容，后续可用 page_id 调用 notion_core_cache_update 编辑。不包含读后感列。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "最多返回条数，默认 30", "default": 30},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "notion_core_cache_update",
                    "description": "按 page_id 更新待审表中一条的字段（只更新传入的字段，不碰读后感）。page_id 从 notion_core_cache_list 得到。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string", "description": "待审表条目的页面 ID"},
                            "content": {"type": "string", "description": "内容（可选）"},
                            "tag": {"type": "string", "description": "分类：图书馆 / 书房 / 客厅（可选）"},
                            "importance": {"type": "integer", "description": "1-4（可选）"},
                            "mention_count": {"type": "integer", "description": "提及次数（可选）"},
                            "promoted_by": {"type": "string", "description": "importance 或 mention_count（可选）"},
                        },
                        "required": ["page_id"],
                    },
                },
            },
        ])
    if NOTION_EXCHANGE_DIARY_DATABASE_ID:
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "notion_diary_list",
                    "description": "列出交换日记条目（标题、心情emoji、正文、提交时间、创建者）。用于读日记内容。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "最多返回条数，默认 20", "default": 20},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "notion_diary_create",
                    "description": "在交换日记里新建一条。创建者传「渡」表示渡写的，传「辛玥」表示代老婆记。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "日记标题（必填其一）"},
                            "content": {"type": "string", "description": "正文内容（必填其一）"},
                            "emoji": {"type": "string", "description": "可选心情，如 😊"},
                            "creator": {"type": "string", "description": "创建者：渡 或 辛玥，默认渡", "default": "渡"},
                        },
                        "required": ["title", "content"],
                    },
                },
            },
        ])
    if NOTION_SCHEDULE_DATABASE_ID:
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "notion_schedule_list",
                    "description": "列出日程本条目（待办/约会/纪念日）。可按类型筛选。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "item_type": {"type": "string", "description": "可选：待办 / 约会 / 纪念日，不传则全部"},
                            "limit": {"type": "integer", "description": "最多返回条数，默认 30", "default": 30},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "notion_schedule_create",
                    "description": "在日程本新建一条。类型必填：待办 / 约会 / 纪念日。待办可传复选框，纪念日可传纪念日日期（文本）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "标题/内容"},
                            "date": {"type": "string", "description": "日期，如 2025-03-15 或 ISO"},
                            "item_type": {"type": "string", "description": "待办 / 约会 / 纪念日"},
                            "checked": {"type": "boolean", "description": "仅待办：是否勾选，默认 false"},
                            "anniversary_date": {"type": "string", "description": "仅纪念日：如 每年3月15日"},
                        },
                        "required": ["content", "date", "item_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "notion_schedule_update",
                    "description": "按 page_id 更新日程本一条（内容、日期、类型、复选框、纪念日日期）。page_id 从 notion_schedule_list 得到。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string", "description": "条目的页面 ID"},
                            "content": {"type": "string", "description": "可选"},
                            "date": {"type": "string", "description": "可选"},
                            "item_type": {"type": "string", "description": "可选：待办/约会/纪念日"},
                            "checked": {"type": "boolean", "description": "可选，仅待办"},
                            "anniversary_date": {"type": "string", "description": "可选，仅纪念日"},
                        },
                        "required": ["page_id"],
                    },
                },
            },
        ])
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
    # 渡的记事本（MiniApp 可见）：写入 R2 的 du_notebook 存储
    tools.append({
        "type": "function",
        "function": {
            "name": "note_write",
            "description": "写入渡的记事本（MiniApp 的“渡的记事本”会显示）。参数：content。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "记事本内容"},
                },
                "required": ["content"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "stay_with_du_write",
            "description": "写入 MiniApp 日常里的 Stay with Du。kind 必填：timeline=重要时间线；movie_want=想一起看的电影；movie_done=一起看过的电影；book_want=想一起读的书；book_done=一起读过的书。title 必填，note/date 可选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "timeline / movie_want / movie_done / book_want / book_done",
                    },
                    "title": {"type": "string", "description": "标题、电影名或书名"},
                    "note": {"type": "string", "description": "可选备注；timeline 时作为节点描述"},
                    "date": {"type": "string", "description": "可选日期，建议 YYYY-MM-DD；timeline 和 done 类不传则默认今天"},
                },
                "required": ["kind", "title"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "stay_with_du_delete",
            "description": "删除 MiniApp 日常里的 Stay with Du 一条记录。kind 必填；优先传 id。没有 id 时可传 title 精确匹配，date 可选用于缩小范围。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "timeline / movie_want / movie_done / book_want / book_done",
                    },
                    "id": {"type": "string", "description": "记录 id，优先使用"},
                    "title": {"type": "string", "description": "没有 id 时用标题、电影名或书名精确匹配"},
                    "date": {"type": "string", "description": "可选日期，用于区分同名条目"},
                },
                "required": ["kind"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "daily_whisper_write",
            "description": "写入 MiniApp 首页“渡今天想说”的气泡文案。可选 date（YYYY-MM-DD），不传默认今天。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "气泡文案内容"},
                    "date": {"type": "string", "description": "可选：YYYY-MM-DD，不传默认今天"},
                },
                "required": ["content"],
            },
        },
    })
    tools.append({
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "当你怀疑当前自动召回的动态记忆不够准或漏了熟悉话题时，主动补检动态记忆层。"
                "只有当当前召回明显和用户这句话对不上，或你强烈怀疑用户在提熟悉主题但召回缺失时才调用。"
                "query 必填，且只能基于用户当前原始消息；不能参考已召回内容来拼 query；"
                "不要为了多搜一遍看看而调用；suspicion_level=low 时禁止调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "必填，只能基于用户当前原始消息"},
                    "scene_type": {"type": "string", "description": "可选：problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict"},
                    "target_type": {"type": "string", "description": "可选：external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic"},
                    "time_range": {"type": "string", "description": "可选：recent_7d / recent_15d / recent_30d / all / between:YYYY-MM-DD,YYYY-MM-DD"},
                    "reason": {"type": "string", "description": "一句话说明为什么怀疑当前召回不够"},
                    "suspicion_level": {"type": "string", "description": "必填：high / medium / low"},
                },
                "required": ["query", "reason", "suspicion_level"],
            },
        },
    })
    if NOTION_CORE_CACHE_DATABASE_ID:
        from services.gateway_tools import get_gateway_sync_tools
        tools.extend(get_gateway_sync_tools())
    from services.weather_almanac import get_weather_almanac_tools
    tools.extend(get_weather_almanac_tools())

    if mode != "daily":
        # active_groups=None 表示全量（expanded）；否则过滤掉未激活组的扩展工具
        if active_groups is not None:
            allowed_extended: Set[str] = frozenset(
                name
                for g_name, g in NOTION_EXTENDED_GROUPS.items()
                if g_name in active_groups
                for name in g["names"]
            )
            tools = [
                t for t in tools
                if (((t.get("function") or {}).get("name") or "") not in _ALL_EXTENDED_NAMES)
                or (((t.get("function") or {}).get("name") or "") in allowed_extended)
            ]
        return tools

    # 日常最小集：只保留高频（日记 + 报时），其余在触发词命中后走 expanded 注入
    keep_names = {"notion_diary_list", "notion_diary_create", "get_time_info", "note_write", "stay_with_du_write", "stay_with_du_delete", "daily_whisper_write"}
    daily_tools = []
    for t in tools:
        fn = (t.get("function") or {}) if isinstance(t, dict) else {}
        name = (fn.get("name") or "").strip()
        if name in keep_names:
            daily_tools.append(t)
    return daily_tools


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
    if name == "publish_html_preview":
        from services.html_preview_tools import execute_publish_html_preview

        return execute_publish_html_preview(arguments if isinstance(arguments, dict) else {})
    if name in SYNC_TOOL_NAMES:
        return execute_gateway_tool(name, arguments)
    if name in ("get_time_info", "get_weather", "get_almanac"):
        from services.weather_almanac import execute_weather_almanac_tool
        return execute_weather_almanac_tool(name, arguments)
    if name == "web_search":
        from services.web_search_tools import execute_web_search
        return execute_web_search(arguments if isinstance(arguments, dict) else {})
    if name == "read_url":
        from services.web_search_tools import execute_read_url
        return execute_read_url(arguments if isinstance(arguments, dict) else {})
    if str(name or "").strip().startswith("maps_"):
        from services.amap_mcp_tools import execute_amap_mcp_tool
        return execute_amap_mcp_tool(name, arguments if isinstance(arguments, dict) else {})
    try:
        from services.amap_mcp_tools import is_amap_mcp_tool
    except Exception:
        is_amap_mcp_tool = None
    if is_amap_mcp_tool and is_amap_mcp_tool(str(name or "").strip()):
        from services.amap_mcp_tools import execute_amap_mcp_tool
        return execute_amap_mcp_tool(name, arguments if isinstance(arguments, dict) else {})
    if name in (
        "forum_read_feed",
        "forum_open_thread",
        "cli",
        "get_guide",
        "schedule_list",
        "schedule_create",
        "schedule_enable",
        "schedule_disable",
        "schedule_delete",
        "search_memory",
        "create_system_alarm",
        "create_calendar_event",
        "show_choice_dialog",
    ):
        return execute_forum_tool(name, arguments)
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

        if name == "notion_read_page_body":
            page_id = (arguments.get("page_id") or "").strip().replace("-", "")
            if not page_id:
                return "page_id 不能为空"
            title, body, err = notion_client.get_page_content_as_text(page_id)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            # 数据库条目常把正文放在 rich_text 属性里，而不是 block children；为空时做属性兜底。
            if not (body or "").strip():
                page, page_err = notion_client.read_page(page_id)
                if not page_err and isinstance(page, dict):
                    body = _collect_rich_text_props_as_body(page)
            return f"标题：{title}\n\n正文：\n{body or '(无正文)'}"

        if name == "notion_append_to_page":
            page_id = (arguments.get("page_id") or "").strip().replace("-", "")
            content = (arguments.get("content") or "").strip()
            ok, msg = _append_content_to_page(page_id, content)
            return msg

        if name == "notion_core_cache_list":
            from services.core_cache_notion_sync import list_pending_entries_for_tools
            limit = int(arguments.get("limit") or 30)
            entries, err = list_pending_entries_for_tools(limit=limit)
            if err:
                return json.dumps({"error": err}, ensure_ascii=False)
            if not entries:
                return "待审表当前无条目。"
            lines = []
            for e in entries:
                lines.append(
                    f"page_id={e['page_id']} | id={e['id']} | tag={e.get('tag')} | importance={e.get('importance')} | "
                    f"content={(e.get('content') or '')[:80]}..."
                )
            return "\n".join(lines)

        if name == "notion_core_cache_update":
            from services.core_cache_notion_sync import update_pending_entry_by_page_id
            page_id = (arguments.get("page_id") or "").strip().replace("-", "")
            if not page_id:
                return "page_id 不能为空"
            content = arguments.get("content")
            if content is not None:
                content = str(content).strip()
            tag = arguments.get("tag")
            if tag is not None:
                tag = str(tag).strip()
            importance = arguments.get("importance")
            if importance is not None:
                try:
                    importance = int(importance)
                except (TypeError, ValueError):
                    importance = None
            mention_count = arguments.get("mention_count")
            if mention_count is not None:
                try:
                    mention_count = int(mention_count)
                except (TypeError, ValueError):
                    mention_count = None
            promoted_by = arguments.get("promoted_by")
            if promoted_by is not None:
                promoted_by = str(promoted_by).strip()
            ok, msg = update_pending_entry_by_page_id(
                page_id, content=content, tag=tag, importance=importance,
                mention_count=mention_count, promoted_by=promoted_by,
            )
            return msg if ok else json.dumps({"error": msg}, ensure_ascii=False)

        if name == "notion_diary_list":
            if not NOTION_EXCHANGE_DIARY_DATABASE_ID:
                return "未配置交换日记数据库"
            name_to_id, name_to_type, err = notion_client.get_database_schema(NOTION_EXCHANGE_DIARY_DATABASE_ID)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            limit = int(arguments.get("limit") or 20)
            _name_to_type = name_to_type or {}
            sorts = None
            if "提交时间" in name_to_id:
                sorts = [{"property": name_to_id["提交时间"], "direction": "descending"}]
            data, err = notion_client.query_database(
                NOTION_EXCHANGE_DIARY_DATABASE_ID,
                sorts=sorts,
                page_size=limit,
            )
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            lines = []
            for page in (data or {}).get("results") or []:
                pid = page.get("id")
                title = _extract_first_nonempty_prop(page, name_to_id, ["标题", "Title", "名称"], "title")
                body = _extract_first_nonempty_prop(page, name_to_id, ["正文", "Content", "内容", "Body"], "rich_text")
                emoji = _extract_first_nonempty_prop(page, name_to_id, ["心情emoji", "emoji"], "rich_text")
                created_type = _name_to_type.get("提交时间", "created_time")
                created = _extract_prop_from_page(page, name_to_id.get("提交时间") or "", created_type) if name_to_id.get("提交时间") else ""
                creator = _extract_first_nonempty_prop(page, name_to_id, ["创建者", "Creator"], "select")
                # 不再截断正文，避免模型拿不到完整日记。
                lines.append(
                    f"page_id={pid} | 标题={title} | 创建者={creator} | 提交时间={created} | 心情={emoji} | 正文={body}"
                )
            return "\n\n".join(lines) if lines else "暂无日记条目。"

        if name == "notion_diary_create":
            if not NOTION_EXCHANGE_DIARY_DATABASE_ID:
                return "未配置交换日记数据库"
            if not isinstance(arguments, dict):
                logger.warning("notion_diary_create arguments 不是 dict，类型=%s", type(arguments).__name__)
                arguments = {}
            # 排查「渡说都写了但报至少填一个」：打工具入参和解析结果，便于看 Notion 日志
            logger.info("notion_diary_create 入参 keys=%s", list(arguments.keys()))
            name_to_id, _, err = notion_client.get_database_schema(NOTION_EXCHANGE_DIARY_DATABASE_ID)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            # schema 已改为英文 key（title/content/creator/emoji）避免渡搞混；兼容旧的中文与 __/___ 等
            def _get_arg(*keys):
                for k in keys:
                    v = arguments.get(k)
                    if v is not None and str(v).strip():
                        return str(v).strip()
                return ""
            title = _get_arg("title", "标题", "__")
            body = _get_arg("content", "正文", "body", "___")
            creator = _get_arg("creator", "创建者", "___1") or "渡"
            emoji = _get_arg("emoji", "心情emoji", "__emoji")
            logger.info("notion_diary_create 解析后 title_len=%s body_len=%s title_preview=%s", len(title), len(body), (title or "")[:80])
            if not title and not body:
                return "标题和正文至少填一个"
            # 解析「标题」「正文」对应的 Notion 属性 id（数据库列名可能是中文或英文）
            title_prop_id = name_to_id.get("标题") or name_to_id.get("Title") or name_to_id.get("名称")
            body_prop_id = name_to_id.get("正文") or name_to_id.get("Content") or name_to_id.get("Body") or name_to_id.get("内容")
            if not title_prop_id and not body_prop_id:
                return "交换日记数据库里需要有一列叫「标题」或 Title、一列叫「正文」或 Content，请检查 Notion 列名。"
            props = {}
            if title_prop_id:
                props[title_prop_id] = _prop_title(title or body[:50])
            if body_prop_id:
                props[body_prop_id] = _prop_rich(body)
            if name_to_id.get("创建者") or name_to_id.get("Creator"):
                creator_id = name_to_id.get("创建者") or name_to_id.get("Creator")
                props[creator_id] = _prop_select(creator)
            if emoji:
                emoji_id = name_to_id.get("心情emoji") or name_to_id.get("emoji")
                if emoji_id:
                    props[emoji_id] = _prop_rich(emoji)
            _, err = notion_client.create_page(
                parent={"database_id": NOTION_EXCHANGE_DIARY_DATABASE_ID},
                properties=props,
            )
            if err:
                err_msg = err.get("error", str(err)) if isinstance(err, dict) else str(err)
                logger.warning("Notion 交换日记写入失败 err=%s", err_msg)
                return f"Notion 写入失败：{err_msg}"
            return "已写入交换日记。"

        if name == "notion_schedule_list":
            if not NOTION_SCHEDULE_DATABASE_ID:
                return "未配置日程本数据库"
            name_to_id, _, err = notion_client.get_database_schema(NOTION_SCHEDULE_DATABASE_ID)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            limit = int(arguments.get("limit") or 30)
            typ = (arguments.get("item_type") or arguments.get("类型") or "").strip()
            tid = name_to_id.get("类型")
            filt = {"property": tid, "select": {"equals": typ}} if typ and tid else None
            data, err = notion_client.query_database(
                NOTION_SCHEDULE_DATABASE_ID,
                filter_obj=filt,
                page_size=limit,
            )
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            lines = []
            for page in (data or {}).get("results") or []:
                pid = page.get("id")
                content = _extract_prop_from_page(page, name_to_id.get("内容") or "", "title") if name_to_id.get("内容") else ""
                date = _extract_prop_from_page(page, name_to_id.get("日期") or "", "date") if name_to_id.get("日期") else ""
                typ_val = _extract_prop_from_page(page, name_to_id.get("类型") or "", "select") if name_to_id.get("类型") else ""
                cb = _extract_prop_from_page(page, name_to_id.get("复选框") or "", "checkbox") if name_to_id.get("复选框") else None
                ann = _extract_prop_from_page(page, name_to_id.get("纪念日日期") or "", "rich_text") if name_to_id.get("纪念日日期") else ""
                parts = [f"page_id={pid}", f"内容={content}", f"日期={date}", f"类型={typ_val}"]
                if cb is not None:
                    parts.append(f"复选框={cb}")
                if ann:
                    parts.append(f"纪念日日期={ann}")
                lines.append(" | ".join(parts))
            return "\n".join(lines) if lines else "暂无日程条目。"

        if name == "notion_schedule_create":
            if not NOTION_SCHEDULE_DATABASE_ID:
                return "未配置日程本数据库"
            name_to_id, _, err = notion_client.get_database_schema(NOTION_SCHEDULE_DATABASE_ID)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            content = (arguments.get("content") or arguments.get("内容") or "").strip()
            date = (arguments.get("date") or arguments.get("日期") or "").strip()
            typ = (arguments.get("item_type") or arguments.get("类型") or "").strip()
            if not content or not typ:
                return "内容、类型为必填"
            props = {}
            if name_to_id.get("内容"):
                props[name_to_id["内容"]] = _prop_title(content)
            if name_to_id.get("日期"):
                props[name_to_id["日期"]] = _prop_date(date)
            if name_to_id.get("类型"):
                props[name_to_id["类型"]] = _prop_select(typ)
            checked_arg = arguments.get("checked")
            if checked_arg is None:
                checked_arg = arguments.get("复选框")
            ann_arg = arguments.get("anniversary_date")
            if ann_arg is None:
                ann_arg = arguments.get("纪念日日期")
            if name_to_id.get("复选框") and typ == "待办":
                props[name_to_id["复选框"]] = _prop_checkbox(bool(checked_arg))
            if name_to_id.get("纪念日日期") and typ == "纪念日" and ann_arg:
                props[name_to_id["纪念日日期"]] = _prop_rich(str(ann_arg).strip())
            _, err = notion_client.create_page(
                parent={"database_id": NOTION_SCHEDULE_DATABASE_ID},
                properties=props,
            )
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            return "已写入日程本。"

        if name == "notion_schedule_update":
            if not NOTION_SCHEDULE_DATABASE_ID:
                return "未配置日程本数据库"
            name_to_id, _, err = notion_client.get_database_schema(NOTION_SCHEDULE_DATABASE_ID)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            page_id = (arguments.get("page_id") or "").strip().replace("-", "")
            if not page_id:
                return "page_id 不能为空"
            props = {}
            content_arg = arguments.get("content")
            if content_arg is None:
                content_arg = arguments.get("内容")
            date_arg = arguments.get("date")
            if date_arg is None:
                date_arg = arguments.get("日期")
            type_arg = arguments.get("item_type")
            if type_arg is None:
                type_arg = arguments.get("类型")
            checked_arg = arguments.get("checked")
            if checked_arg is None:
                checked_arg = arguments.get("复选框")
            ann_arg = arguments.get("anniversary_date")
            if ann_arg is None:
                ann_arg = arguments.get("纪念日日期")
            if "内容" in name_to_id and content_arg is not None:
                props[name_to_id["内容"]] = _prop_title(str(content_arg).strip())
            if "日期" in name_to_id and date_arg is not None:
                props[name_to_id["日期"]] = _prop_date(str(date_arg).strip())
            if "类型" in name_to_id and type_arg is not None:
                props[name_to_id["类型"]] = _prop_select(str(type_arg).strip())
            if "复选框" in name_to_id and checked_arg is not None:
                props[name_to_id["复选框"]] = _prop_checkbox(bool(checked_arg))
            if "纪念日日期" in name_to_id and ann_arg is not None:
                props[name_to_id["纪念日日期"]] = _prop_rich(str(ann_arg).strip())
            if not props:
                return "未传入要更新的字段"
            _, err = notion_client.update_page(page_id, props)
            if err:
                return json.dumps({"error": str(err)}, ensure_ascii=False)
            return "已更新日程本条目。"

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

        if name == "note_write":
            from storage import r2_store
            content = _normalize_note_write_content(arguments.get("content") or "")
            if not content:
                return "content 为空"
            entry = r2_store.add_du_notebook_entry(content)
            if not entry:
                return "写入失败"
            return f"写入成功 id={entry.get('id')} updated_at={entry.get('updated_at')}"

        if name == "stay_with_du_write":
            from storage import r2_store
            kind = (arguments.get("kind") or "").strip()
            title = (arguments.get("title") or "").strip()
            note = (arguments.get("note") or "").strip()
            date = (arguments.get("date") or "").strip()
            if not kind:
                return "kind 为空"
            if not title:
                return "title 为空"
            entry = r2_store.add_stay_with_du_entry(kind=kind, title=title, note=note, date=date)
            if not entry:
                return "写入失败：kind 只能是 timeline/movie_want/movie_done/book_want/book_done"
            return f"写入成功 id={entry.get('id')} kind={kind}"

        if name == "stay_with_du_delete":
            from storage import r2_store
            kind = (arguments.get("kind") or "").strip()
            entry_id = (arguments.get("id") or "").strip()
            title = (arguments.get("title") or "").strip()
            date = (arguments.get("date") or "").strip()
            if not kind:
                return "kind 为空"
            if not entry_id and not title:
                return "id 和 title 至少传一个"
            deleted = r2_store.delete_stay_with_du_entry(kind=kind, entry_id=entry_id, title=title, date=date)
            if not deleted:
                return "删除失败：kind 不合法，或没有找到匹配记录"
            return f"删除成功 id={deleted.get('id')} title={deleted.get('title')}"

        if name == "daily_whisper_write":
            from storage import r2_store
            content = (arguments.get("content") or "").strip()
            if not content:
                return "content 为空"
            date = (arguments.get("date") or "").strip()
            if not date:
                date = today_beijing()
            payload = {
                "date": date,
                "text": content,
                "updatedAt": now_beijing_iso(),
                "by": "du_tool",
            }
            ok = r2_store.save_miniapp_daily_whisper(payload)
            if not ok:
                return "写入失败"
            return f"写入成功 date={date}"

        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.exception("Notion 工具执行异常 name=%s", name)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
