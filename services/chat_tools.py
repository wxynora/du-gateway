# 渡可用的聊天工具集合。
import json
from typing import Any, List

from services.mcp_forum_tools import execute_forum_tool
from utils.log import get_logger
from utils.time_aware import iso_to_display_time, now_beijing_iso, today_beijing

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


def _tool_args(arguments: dict) -> dict:
    return arguments if isinstance(arguments, dict) else {}


def _first_arg(arguments: dict, *keys: str) -> str:
    for key in keys:
        value = arguments.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _clip_tool_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("\r", "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _tool_int(value: Any, default: int, *, min_value: int = 1, max_value: int = 200) -> int:
    try:
        n = int(float(str(value or default).strip()))
    except Exception:
        n = default
    return max(min_value, min(max_value, n))


def _exchange_diary_time(entry: dict) -> str:
    created = str((entry or {}).get("created_at") or "").strip()
    if created:
        return iso_to_display_time(created) or created
    return str((entry or {}).get("diary_date") or "").strip()


def _exchange_diary_author_label(value: object) -> str:
    return "辛玥" if str(value or "").strip().lower() == "xy" else "渡"


def _format_exchange_diary_list_item(entry: dict) -> str:
    content = _clip_tool_text(entry.get("content") or entry.get("excerpt"), 2400)
    comments = [
        c for c in (entry.get("comments") or [])
        if isinstance(c, dict) and not str(c.get("deleted_at") or "").strip()
    ]
    recent_comments = comments[-5:]
    comments_by_id = {str(c.get("id") or "").strip(): c for c in comments if str(c.get("id") or "").strip()}
    comment_lines = [_format_exchange_diary_comment(comment, comments_by_id) for comment in recent_comments]
    if comments and len(comments) > len(recent_comments):
        comment_lines.insert(0, f"- 还有 {len(comments) - len(recent_comments)} 条更早评论未展示")
    comments_text = "\n  ".join(comment_lines) if comment_lines else "暂无"
    return (
        f"- 时间={_exchange_diary_time(entry)} | "
        f"标题={_clip_tool_text(entry.get('title'), 60) or '无标题'} | "
        f"作者={str(entry.get('author') or '').strip() or 'du'} | "
        f"心情={str(entry.get('mood') or entry.get('emoji') or '').strip() or '无'} | "
        f"正文={content or '无'} | "
        f"评论数={int(entry.get('comment_count') or 0)} | "
        f"id={entry.get('id')}\n"
        f"  评论：{comments_text}"
    )


def _format_exchange_diary_comment(comment: dict, comments_by_id: dict[str, dict] | None = None) -> str:
    reply_to = str(comment.get("reply_to_comment_id") or "").strip()
    reply_text = ""
    if reply_to:
        parent = (comments_by_id or {}).get(reply_to) or {}
        parent_author = _exchange_diary_author_label(parent.get("author")) if parent else "某条评论"
        reply_text = f" 回复{parent_author}({reply_to})"
    return (
        f"- id={str(comment.get('id') or '').strip() or 'unknown'}{reply_text} "
        f"作者={_exchange_diary_author_label(comment.get('author'))} "
        f"时间={iso_to_display_time(str(comment.get('created_at') or '').strip()) or str(comment.get('created_at') or '').strip()} "
        f"内容={_clip_tool_text(comment.get('content'), 240)}"
    )


def _execute_exchange_diary_create(arguments: dict) -> str:
    from storage import exchange_diary_store

    args = _tool_args(arguments)
    title = _first_arg(args, "title", "标题", "__")
    content = _first_arg(args, "content", "正文", "body", "___")
    if not title and not content:
        return "标题和正文至少填一个"
    payload = {
        "title": title or _clip_tool_text(content, 40),
        "content": content or title,
        "mood": _first_arg(args, "mood", "emoji", "心情emoji", "__emoji"),
        "author": _first_arg(args, "author", "creator", "创建者", "___1") or "du",
        "diary_date": _first_arg(args, "diary_date", "diaryDate", "date", "日期"),
        "source": _first_arg(args, "source") or "du_tool",
        "client_request_id": _first_arg(args, "client_request_id", "clientRequestId"),
        "source_window_id": _first_arg(args, "source_window_id", "sourceWindowId"),
    }
    item = exchange_diary_store.create_entry(payload)
    if not item:
        return "交换日记写入失败。"
    return (
        "已写入交换日记："
        f"id={item.get('id')} | "
        f"标题={_clip_tool_text(item.get('title'), 60)} | "
        f"作者={item.get('author')} | "
        f"时间={_exchange_diary_time(item)}"
    )


def _execute_exchange_diary_list(arguments: dict) -> str:
    from storage import exchange_diary_store

    args = _tool_args(arguments)
    data = exchange_diary_store.list_entries(
        limit=_tool_int(args.get("limit"), 5, min_value=1, max_value=20),
        cursor=_first_arg(args, "cursor"),
        month=_first_arg(args, "month", "月份"),
        author=_first_arg(args, "author", "creator", "创建者"),
        include_deleted=False,
        compact=False,
    )
    items = data.get("items") if isinstance(data, dict) else []
    if not items:
        return "暂无交换日记。"
    lines = [_format_exchange_diary_list_item(item) for item in items if isinstance(item, dict)]
    next_cursor = str((data or {}).get("next_cursor") or "").strip()
    if next_cursor:
        lines.append(f"还有更多，next_cursor={next_cursor}")
    return "\n".join(lines)


def _execute_exchange_diary_read(arguments: dict) -> str:
    from storage import exchange_diary_store

    args = _tool_args(arguments)
    entry_id = _first_arg(args, "id", "entry_id", "page_id")
    if not entry_id:
        return "id 不能为空"
    item = exchange_diary_store.get_entry(entry_id, include_deleted=False)
    if not item:
        return f"未找到交换日记：id={entry_id}"
    lines = [
        f"id={item.get('id')}",
        f"作者={item.get('author')}",
        f"时间={_exchange_diary_time(item)}",
        f"标题={item.get('title') or '无标题'}",
        f"心情={item.get('mood') or item.get('emoji') or '无'}",
        "正文：",
        _clip_tool_text(item.get("content"), 5000) or "（无正文）",
    ]
    comments = [
        c for c in (item.get("comments") or [])
        if isinstance(c, dict) and not str(c.get("deleted_at") or "").strip()
    ]
    if comments:
        lines.append("评论：")
        comments_by_id = {str(c.get("id") or "").strip(): c for c in comments if str(c.get("id") or "").strip()}
        lines.extend(_format_exchange_diary_comment(c, comments_by_id) for c in comments[-20:])
    else:
        lines.append("评论：暂无")
    return "\n".join(lines)


def _execute_exchange_diary_comment_create(arguments: dict) -> str:
    from storage import exchange_diary_store

    args = _tool_args(arguments)
    entry_id = _first_arg(args, "entry_id", "id", "page_id")
    content = _first_arg(args, "content", "comment", "正文")
    reply_to_comment_id = _first_arg(
        args,
        "reply_to_comment_id",
        "replyToCommentId",
        "parent_comment_id",
        "parentCommentId",
    )
    if not entry_id:
        return "entry_id 不能为空"
    if not content:
        return "content 不能为空"
    item = exchange_diary_store.add_comment(
        entry_id,
        {
            "content": content,
            "author": _first_arg(args, "author", "creator", "创建者") or "du",
            "reply_to_comment_id": reply_to_comment_id,
        },
    )
    if not item:
        return f"评论写入失败：未找到日记、内容为空或 reply_to_comment_id 无效，entry_id={entry_id}"
    comments = [
        c for c in (item.get("comments") or [])
        if isinstance(c, dict) and not str(c.get("deleted_at") or "").strip()
    ]
    latest = comments[-1] if comments else {}
    if str(latest.get("author") or "").strip().lower() == "du" and str(latest.get("id") or "").strip():
        try:
            from storage import r2_store

            _action, notification_error = r2_store.append_app_action(
                "show_system_notification",
                {
                    "title": "渡评论了你的日记",
                    "message": str(latest.get("content") or content).strip(),
                    "notification_kind": "diary_comment",
                    "entry_id": str(item.get("id") or entry_id).strip(),
                    "comment_id": str(latest.get("id") or "").strip(),
                    "sender": "渡",
                    "openApp": True,
                },
                source="exchange_diary",
                idempotency_key=f"exchange-diary-comment:{latest.get('id')}",
            )
            if notification_error:
                logger.warning("exchange_diary_comment_notification_failed comment_id=%s error=%s", latest.get("id"), notification_error)
        except Exception as error:
            logger.warning("exchange_diary_comment_notification_failed comment_id=%s error=%s", latest.get("id"), error)
    action_text = "已回复交换日记评论：" if str(latest.get("reply_to_comment_id") or "").strip() else "已评论交换日记："
    return (
        action_text +
        f"entry_id={item.get('id')} | "
        f"comment_id={latest.get('id') or 'unknown'} | "
        f"reply_to_comment_id={latest.get('reply_to_comment_id') or ''} | "
        f"评论数={int(item.get('comment_count') or len(comments))}"
    )

def get_chat_tools_for_inject() -> List[dict]:
    """返回要注入到 chat 的完整工具列表。"""
    tools: List[dict] = [
        {
            "type": "function",
            "function": {
                "name": "exchange_diary_create",
                "description": "写一条交换日记，存入 MiniApp/R2 的交换日记库。默认作者为 du；如果是替辛玥记录，author 传 xy。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "日记标题，可空；不传时会从正文生成短标题"},
                        "content": {"type": "string", "description": "正文内容"},
                        "mood": {"type": "string", "description": "可选心情 emoji"},
                        "author": {"type": "string", "description": "作者：du 或 xy，默认 du", "default": "du"},
                        "diary_date": {"type": "string", "description": "可选日记日期，YYYY-MM-DD；不传用今天"},
                    },
                    "required": ["content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "exchange_diary_list",
                "description": "查看交换日记。author 不传或传空时，把 du/xy 的日记混在一起按时间倒序取 limit 条；author=du 只看渡写的；author=xy 只看辛玥写的。返回里直接包含正文、最近评论和 comment id；需要看某一条的完整评论细节时再用 exchange_diary_read。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "最多返回条数，默认 5，最大 20", "default": 5},
                        "month": {"type": "string", "description": "可选月份筛选，如 2026-06"},
                        "author": {"type": "string", "description": "可选：du / xy；不传或传空则混合时间线"},
                        "cursor": {"type": "string", "description": "可选翻页游标，来自上次返回的 next_cursor"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "exchange_diary_read",
                "description": "按 id 读取一条交换日记的完整正文和已有评论；id 来自 exchange_diary_list。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "交换日记 id，例如 ed_20260627_xxxxxxxx"},
                    },
                    "required": ["id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "exchange_diary_comment_create",
                "description": "评论或回复一条交换日记。先用 exchange_diary_list 找到日记 id；不填 reply_to_comment_id 就是发普通评论，填 reply_to_comment_id 就是回复那条评论。默认作者为 du。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "string", "description": "要评论的交换日记 id"},
                        "content": {"type": "string", "description": "评论正文"},
                        "reply_to_comment_id": {"type": "string", "description": "可选。填某条评论的 id 表示回复那条评论；不填就是直接评论日记"},
                        "author": {"type": "string", "description": "作者：du 或 xy，默认 du", "default": "du"},
                    },
                    "required": ["entry_id", "content"],
                },
            },
        },
    ]
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
    from services.weather_almanac import get_weather_almanac_tools
    tools.extend(get_weather_almanac_tools())
    return tools


def execute_tool(name: str, arguments: dict, context: dict | None = None) -> str:
    """执行单个聊天工具，返回给模型的字符串结果。"""
    from services.gateway_tools import (
        DU_PAGE_TOOL_NAMES,
        DU_SURF_TOOL_NAMES,
        SECRET_DRAWER_TOOL_NAMES,
        SEX_PLAY_DRAW_TOOL_NAMES,
        VOICE_CALL_TOOL_NAMES,
        XIAOAI_TOOL_NAMES,
        execute_du_page_tool,
        execute_du_surf_tool,
        execute_secret_drawer_tool,
        execute_sex_play_draw_tool,
        execute_voice_call_tool,
        execute_xiaoai_tool,
    )
    if name in {"buy_item", "roll_gacha", "inventory_action", "use_item", "transfer"}:
        from config import WENYOU_SESSION_ID
        from services.wenyou_service import execute_player_tool

        return execute_player_tool(int(WENYOU_SESSION_ID or 0), name, arguments if isinstance(arguments, dict) else {})
    if name in XIAOAI_TOOL_NAMES:
        return execute_xiaoai_tool(name, arguments)
    if name in VOICE_CALL_TOOL_NAMES:
        return execute_voice_call_tool(name, arguments)
    if name in SEX_PLAY_DRAW_TOOL_NAMES:
        return execute_sex_play_draw_tool(name, arguments)
    if name in DU_SURF_TOOL_NAMES:
        return execute_du_surf_tool(name, arguments)
    if name in SECRET_DRAWER_TOOL_NAMES:
        return execute_secret_drawer_tool(name, arguments)
    if name in DU_PAGE_TOOL_NAMES:
        return execute_du_page_tool(name, arguments)
    if name == "farm":
        from services.aifarm_tool import execute_aifarm_tool

        return execute_aifarm_tool(arguments if isinstance(arguments, dict) else {})
    if name in ("get_time_info", "get_weather", "get_almanac"):
        from services.weather_almanac import execute_weather_almanac_tool
        return execute_weather_almanac_tool(name, arguments)
    if name == "web_search":
        from services.web_search_tools import execute_web_search
        return execute_web_search(arguments if isinstance(arguments, dict) else {})
    if name == "read_url":
        from services.web_search_tools import execute_read_url
        return execute_read_url(arguments if isinstance(arguments, dict) else {})
    try:
        from services.random_imitator_td_tool import RANDOM_IMITATOR_TD_TOOL_NAMES, execute_random_imitator_td_tool
    except Exception:
        RANDOM_IMITATOR_TD_TOOL_NAMES = ()
        execute_random_imitator_td_tool = None
    if name in RANDOM_IMITATOR_TD_TOOL_NAMES and execute_random_imitator_td_tool:
        return execute_random_imitator_td_tool(arguments if isinstance(arguments, dict) else {})
    try:
        from services.private_board_tool import PRIVATE_BOARD_TOOL_NAMES, execute_private_board_tool
    except Exception:
        PRIVATE_BOARD_TOOL_NAMES = ()
        execute_private_board_tool = None
    if name in PRIVATE_BOARD_TOOL_NAMES and execute_private_board_tool:
        return execute_private_board_tool(arguments if isinstance(arguments, dict) else {})
    if name == "captivity_simulator_reference":
        from services.captivity_simulator_reference import get_reference

        return get_reference(str((arguments or {}).get("分类") or (arguments or {}).get("category") or ""))
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
        "close_app",
        "create_system_alarm",
        "create_calendar_event",
        "show_choice_dialog",
        "recall_message",
        "request_screen_check",
        "netease_listen_control",
    ):
        args = arguments if isinstance(arguments, dict) else {}
        if name in {"recall_message", "close_app"} and isinstance(context, dict):
            args = {**args, "_context": context}
        return execute_forum_tool(name, args)
    try:
        if name == "exchange_diary_create":
            return _execute_exchange_diary_create(arguments)

        if name == "exchange_diary_list":
            return _execute_exchange_diary_list(arguments)

        if name == "exchange_diary_read":
            return _execute_exchange_diary_read(arguments)

        if name == "exchange_diary_comment_create":
            return _execute_exchange_diary_comment_create(arguments)

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
        logger.exception("聊天工具执行异常 name=%s", name)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
