"""Compact, local-only history of completed gateway tool calls."""

from __future__ import annotations

import copy
import hashlib
import json
import queue
import re
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from config import (
    CHAT_RESPONSE_TIMEOUT_SECONDS,
    SILICONFLOW_BASE_HOST,
    TOOL_RESULT_CACHE_MAX_CHARS,
    TOOL_RESULT_CACHE_TRIM_TO_CHARS,
    TOOL_RESULT_CACHE_TTL_SECONDS,
    TOOL_RESULT_HOT_MAX_CHARS,
    resolve_siliconflow_api_key,
)
from storage import runtime_sqlite
from utils.log import get_logger

logger = get_logger(__name__)

TOOL_RESULT_CACHE_SYSTEM_MARKER = "__tool_result_cache__"
FROZEN_TOOL_SUMMARY_SYSTEM_MARKER = "__frozen_tool_summary__"
HOT_TOOL_RESULT_SYSTEM_MARKER = "__hot_tool_result__"
_BEIJING = ZoneInfo("Asia/Shanghai")
_SPACE_RE = re.compile(r"\s+")
_SECRET_RE = re.compile(
    r"(?i)((?:api[_-]?key|authorization|cookie|password|passwd|secret|token|access[_-]?token|refresh[_-]?token)\s*[:=]\s*)([^,}\]\s]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
_PROMPT_HEADER = (
    "【最近24小时工具使用摘要】\n"
    "以下是你已经完成的工具调用摘要，只用于记住刚才做过什么；需要最新结果时仍可重新调用工具。"
)
_FROZEN_PROMPT_HEADER = (
    "〖已归档工具摘要〗\n"
    "以下内容是当前缓存代际开始时已经存在的工具调用摘要。\n"
    "需要当前状态时仍以新的工具调用结果为准。"
)
_HOT_PROMPT_HEADER = (
    "〖本代新增工具结果〗\n"
    "以下工具结果产生于当前缓存代际，时间晚于前面的已归档工具摘要。\n"
    "同一事项存在冲突时，以这里时间更晚的结果为准。"
)
_GAME_LOOP_SUMMARY_MODEL = "Qwen/Qwen3-8B"
_GAME_LOOP_SUMMARY_TOOLS = frozenset({"random_imitator_td", "farm", "cedareco", "travel"})
_GAME_LOOP_SUMMARY_SYSTEM_PROMPT = """你负责把同一轮单机游戏中的连续工具调用记录融合成一条准确、自然的中文历史摘要。

严格按照记录顺序整理，只写记录中实际发生的内容。
保留实际执行的动作、关键状态变化、资源获得或消耗、失败原因和终局结果；相同状态只合并表达一次，不得遗漏会影响后续游戏判断的信息。
忽略每次结果中重复出现的游戏规则、操作方法、命令说明、字段说明、固定 system/guide、协议标记、界面标题和其他不会随本轮操作变化的固定文字。只有某条规则在本轮发生变化，或实际触发并直接影响本轮结果时，才保留与该结果有关的部分。
不得编造、推测或评价操作，不要使用第一人称或第二人称。
只输出一条完整正文，不输出标题、列表、Markdown、JSON、解释或前后缀。"""
_GAME_LOOP_SUMMARY_QUEUE: queue.Queue = queue.Queue()
_GAME_LOOP_SUMMARY_THREAD: threading.Thread | None = None
_GAME_LOOP_SUMMARY_THREAD_LOCK = threading.Lock()


def _text(value: Any, max_chars: int = 600) -> str:
    raw = str(value or "").replace("\r", " ").replace("\n", " ")
    raw = _SPACE_RE.sub(" ", raw).strip()
    raw = _SECRET_RE.sub(lambda m: f"{m.group(1)}***", raw)
    raw = _BEARER_RE.sub("Bearer ***", raw)
    if len(raw) > max_chars:
        raw = raw[:max_chars].rstrip(" ，,。；;:") + "…"
    return raw


def _text_without_limit(value: Any) -> str:
    raw = str(value or "").replace("\r", " ").replace("\n", " ")
    raw = _SPACE_RE.sub(" ", raw).strip()
    raw = _SECRET_RE.sub(lambda m: f"{m.group(1)}***", raw)
    return _BEARER_RE.sub("Bearer ***", raw)


def _dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _tags(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value] if value else []
    out: list[str] = []
    for item in raw:
        tag = _text(item, 40)
        if tag and tag not in out:
            out.append(tag)
    return out[:6]


def _item_label(item: dict) -> str:
    title = _text(item.get("title") or item.get("name"), 80)
    item_type = _text(item.get("type"), 30)
    if title:
        return f"{item_type}《{title}》" if item_type else f"《{title}》"
    return item_type or "一条记录"


def _failure_detail(data: dict, fallback: str = "执行失败") -> str:
    return _text(data.get("error") or data.get("message") or fallback, 240)


def _secret_drawer_detail(arguments: dict, data: dict) -> str:
    action = _text(arguments.get("action"), 30).lower()
    payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else {}
    if not data.get("ok", True):
        return _failure_detail(data, "秘密抽屉操作失败")

    item = data.get("item") if isinstance(data.get("item"), dict) else {}
    effective = item or payload
    label = _item_label(effective)
    tags = _tags(effective.get("tags"))
    tag_text = f"；标签：{'、'.join(tags)}" if tags else ""
    if action in {"save", "create"} or action.startswith("save_"):
        return f"存下了{label}{tag_text}"
    if action == "update":
        changed: list[str] = []
        if "title" in payload:
            changed.append(f"标题改为《{_text(payload.get('title'), 80)}》")
        if "type" in payload:
            changed.append(f"类型改为{_text(payload.get('type'), 30)}")
        if "tags" in payload:
            changed.append(f"标签改为{'、'.join(_tags(payload.get('tags'))) or '无'}")
        if "why" in payload:
            changed.append("补充了整理说明")
        if "content" in payload:
            changed.append("整理了正文")
        return f"整理了{label}" + (f"；{'；'.join(changed)}" if changed else tag_text)
    if action == "delete":
        return f"删除了{label}"
    if action == "restore":
        return f"恢复了{label}"
    if action in {"get", "random"}:
        return f"翻到{label}{tag_text}"
    if action == "list":
        items = data.get("items") if isinstance(data.get("items"), list) else []
        names = [_item_label(row) for row in items[:5] if isinstance(row, dict)]
        return f"列出{int(data.get('count') or len(items))}条" + (f"：{'、'.join(names)}" if names else "")
    if action == "stats":
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        return f"查看概况：共{int(stats.get('total') or 0)}条"
    if action == "set_pin":
        return "更新了解锁设置"
    return f"处理了{label}{tag_text}"


def _collect_titles(value: Any, out: list[str], limit: int = 5) -> None:
    if len(out) >= limit:
        return
    if isinstance(value, dict):
        for key in ("title", "subject", "name"):
            title = _text(value.get(key), 90)
            if title and title not in out:
                out.append(title)
                if len(out) >= limit:
                    return
        for child in value.values():
            _collect_titles(child, out, limit)
            if len(out) >= limit:
                return
    elif isinstance(value, list):
        for child in value:
            _collect_titles(child, out, limit)
            if len(out) >= limit:
                return


def _forum_detail(name: str, arguments: dict, data: dict) -> str:
    if not data.get("ok", True):
        return _failure_detail(data, "论坛工具执行失败")
    command = _text(arguments.get("command"), 160)
    structured = data.get("structured_content")
    titles: list[str] = []
    _collect_titles(structured, titles)
    content = _text(data.get("content"), 300)
    if name == "forum_read_feed" or command.startswith("list"):
        return "浏览论坛动态" + (f"：看到《{'》《'.join(titles)}》" if titles else f"：{content}" if content else "")
    if name == "forum_open_thread" or command.startswith("show"):
        target = f"《{titles[0]}》" if titles else _text(arguments.get("post_id"), 80) or "帖子"
        return f"阅读了{target}" + (f"：{content}" if content else "")
    verb = "使用论坛工具"
    lowered = command.lower()
    if lowered.startswith(("post", "create")):
        verb = "发布了帖子"
    elif lowered.startswith(("reply", "comment")):
        verb = "回复了帖子"
    elif lowered.startswith("like"):
        verb = "点赞了帖子"
    return verb + (f"：{content}" if content else f"（{command}）" if command else "")


_GALATEA_GARDEN_FORUM_ACTIONS = frozenset(
    {
        "list_threads",
        "get_thread",
        "create_thread",
        "create_reply",
        "delete_thread",
        "delete_reply",
        "interact",
        "list_notifications",
        "list_activity",
    }
)


def _galatea_garden_result_payload(data: dict) -> Any:
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, list):
        return None
    for item in content:
        if not isinstance(item, dict) or str(item.get("type") or "").strip().lower() != "text":
            continue
        raw = str(item.get("text") or "").strip()
        if not raw:
            continue
        try:
            return json.loads(raw)
        except Exception:
            continue
    return None


def _galatea_garden_text_content(data: dict) -> str:
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, list):
        return ""
    for item in content:
        if isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "text":
            text = str(item.get("text") or "").strip()
            if text:
                return text
    return ""


def _galatea_garden_titles(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    titles: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"), 90)
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= 5:
            break
    return titles


def _galatea_garden_first_title(payload: Any) -> str:
    if isinstance(payload, dict):
        title = _text(payload.get("title"), 90)
        if title:
            return title
        for key in ("thread", "data", "result"):
            title = _galatea_garden_first_title(payload.get(key))
            if title:
                return title
    return ""


def _galatea_garden_detail(arguments: dict, raw_result: Any, data: dict) -> str:
    action = _text(arguments.get("action"), 40).lower()
    action_args = arguments.get("args") if isinstance(arguments.get("args"), dict) else {}
    if not data.get("ok", True) or data.get("isError") is True:
        failure = data.get("error") or _galatea_garden_text_content(data) or "花园工具执行失败"
        return f"{action or '花园操作'}失败：{_text(failure, 240)}"

    if action == "help":
        target = _text(action_args.get("name"), 60) or "目标操作"
        return f"查看了 {target} 操作说明"
    if action not in _GALATEA_GARDEN_FORUM_ACTIONS:
        return _generic_detail("galatea_garden", arguments, raw_result, data)

    payload = _galatea_garden_result_payload(data)
    if action == "list_notifications":
        notifications = payload if isinstance(payload, list) else []
        titles = _galatea_garden_titles(notifications)
        detail = f"查看花园通知，共{len(notifications)}条"
        return detail + (f"：{'、'.join(f'《{title}》' for title in titles)}" if titles else "")
    if action == "list_threads":
        threads = payload.get("threads") if isinstance(payload, dict) and isinstance(payload.get("threads"), list) else []
        titles = _galatea_garden_titles(threads)
        search = _text(action_args.get("search"), 90)
        detail = f"搜索花园论坛“{search}”，找到{len(threads)}篇" if search else f"浏览花园论坛，共{len(threads)}篇"
        return detail + (f"：{'、'.join(f'《{title}》' for title in titles)}" if titles else "")
    if action == "get_thread":
        thread_id = _text(action_args.get("thread_id"), 40)
        title = _galatea_garden_first_title(payload)
        target = f"《{title}》" if title else f"帖子 {thread_id}" if thread_id else "花园帖子"
        return f"阅读了{target}"
    if action == "create_thread":
        title = _text(action_args.get("title"), 90) or _galatea_garden_first_title(payload)
        return f"发布了花园帖子{f'《{title}》' if title else ''}"
    if action == "create_reply":
        thread_id = _text(action_args.get("thread_id"), 40)
        return f"回复了花园帖子{f'（thread_id={thread_id}）' if thread_id else ''}"
    if action == "delete_thread":
        thread_id = _text(action_args.get("thread_id"), 40)
        return f"删除了花园帖子{f'（thread_id={thread_id}）' if thread_id else ''}"
    if action == "delete_reply":
        reply_id = _text(action_args.get("reply_id"), 40)
        return f"删除了花园回复{f'（reply_id={reply_id}）' if reply_id else ''}"
    if action == "interact":
        kind = _text(action_args.get("kind") or action_args.get("action"), 40)
        target_type = _text(action_args.get("target_type"), 30)
        target_id = _text(action_args.get("target_id"), 40)
        target = ":".join(part for part in (target_type, target_id) if part)
        return f"在花园执行互动{f' {kind}' if kind else ''}{f'（{target}）' if target else ''}"

    activities = payload if isinstance(payload, list) else payload.get("items") if isinstance(payload, dict) and isinstance(payload.get("items"), list) else []
    titles = _galatea_garden_titles(activities)
    detail = f"查看花园动态，共{len(activities)}条"
    return detail + (f"：{'、'.join(f'《{title}》' for title in titles)}" if titles else "")


def _web_search_detail(arguments: dict, data: dict) -> str:
    query = _text(data.get("query") or arguments.get("query"), 160)
    if not data.get("ok", True):
        return f"搜索“{query}”失败：{_failure_detail(data)}"
    items = data.get("items") if isinstance(data.get("items"), list) else []
    compressed = data.get("compressed_pages") if isinstance(data.get("compressed_pages"), list) else []
    titles: list[str] = []
    for row in items[:5]:
        if not isinstance(row, dict):
            continue
        title = _text(row.get("title"), 90)
        if title and title not in titles:
            titles.append(title)
    conclusions: list[str] = []
    for row in compressed[:2]:
        if not isinstance(row, dict) or str(row.get("status") or "") not in {"ok", "truncated"}:
            continue
        content = _text(row.get("content"), 220)
        if content:
            conclusions.append(content)
    detail = f"搜索“{query}”"
    if conclusions:
        detail += f"；结论：{'；'.join(conclusions)}"
    if titles:
        detail += f"；来源：{'、'.join(titles[:3])}"
    return detail


def _game_detail(name: str, arguments: dict, data: dict) -> str:
    command = _text(arguments.get("command") or arguments.get("action"), 120)
    if not data.get("ok", True):
        return f"{command + '；' if command else ''}{_failure_detail(data, '游戏操作失败')}"
    if data.get("game_over"):
        outcome = _text(data.get("result") or data.get("winner") or data.get("text"), 260)
        return f"本局结束{f'：{outcome}' if outcome else ''}"
    result = _text(data.get("text") or data.get("result") or data.get("message"), 300)
    if command and result:
        return f"{command}；{result}"
    return command or result or f"完成{name}操作"


def _memory_search_detail(arguments: dict, data: dict) -> str:
    query = _text(arguments.get("query") or arguments.get("text"), 160)
    items = data.get("items") if isinstance(data.get("items"), list) else data.get("results") if isinstance(data.get("results"), list) else []
    if not data.get("ok", True):
        return f"搜索记忆“{query}”失败：{_failure_detail(data)}"
    return f"搜索记忆“{query}”，命中{len(items)}条"


def _exchange_diary_result_field(raw: str, label: str, max_chars: int = 80) -> str:
    match = re.search(rf"(?m)(?:^-\s*|^|\|\s*){re.escape(label)}=([^|\n]+)", str(raw or ""))
    return _text(match.group(1), max_chars) if match else ""


def _exchange_diary_read_preview(raw: str) -> tuple[str, str]:
    body = ""
    comments = "暂无"
    body_marker = "\n正文：\n"
    comments_marker = "\n评论："
    if body_marker in raw:
        body_and_comments = raw.split(body_marker, 1)[1]
        if comments_marker in body_and_comments:
            body, comments = body_and_comments.split(comments_marker, 1)
        else:
            body = body_and_comments
    return _text(body, 100) or "（无正文）", str(comments or "暂无").strip() or "暂无"


def _exchange_diary_list_entry_preview(raw: str) -> str:
    title = _exchange_diary_result_field(raw, "标题", 80) or "无标题"
    diary_time = _exchange_diary_result_field(raw, "时间", 60)
    body_match = re.search(r"正文=(.*?)\s*\|\s*评论数=", raw, re.DOTALL)
    body = _text(body_match.group(1), 100) if body_match else ""
    comments = raw.split("\n  评论：", 1)[1].strip() if "\n  评论：" in raw else "暂无"
    prefix = f"《{title}》{f'（{diary_time}）' if diary_time else ''}"
    return f"{prefix}：{body or '（无正文）'}；评论：{comments or '暂无'}"


def _exchange_diary_detail(name: str, arguments: dict, raw_result: Any) -> str:
    action = _text(arguments.get("action"), 30).lower()
    if name != "exchange_diary":
        action = {
            "exchange_diary_create": "create",
            "exchange_diary_list": "list",
            "exchange_diary_read": "read",
            "exchange_diary_comment_create": "comment",
        }.get(name, action)

    raw = str(raw_result or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    entry_id = _text(
        arguments.get("entry_id") or arguments.get("id") or arguments.get("page_id"),
        80,
    ) or _exchange_diary_result_field(raw, "entry_id", 80) or _exchange_diary_result_field(raw, "id", 80)

    if action == "create":
        if not raw.startswith("已写入交换日记："):
            return "写交换日记未完成"
        title = _exchange_diary_result_field(raw, "标题", 80)
        created_at = _exchange_diary_result_field(raw, "时间", 60)
        detail = f"写了交换日记{f'《{title}》' if title else ''}"
        return detail + (f"（{created_at}）" if created_at else "")

    if action == "list":
        if raw == "暂无交换日记。":
            return "查看交换日记列表：暂无"
        entries = [
            _exchange_diary_list_entry_preview(block)
            for block in re.split(r"(?m)(?=^- 时间=)", raw)
            if block.startswith("- 时间=")
        ]
        detail = f"查看交换日记列表，共{len(entries)}篇" if entries else "查看交换日记列表"
        return detail + (f"：{'；'.join(entries)}" if entries else "")

    if action == "read":
        if not raw or raw.startswith(("id 不能为空", "未找到交换日记")):
            return f"查看交换日记未完成{f'（{entry_id}）' if entry_id else ''}"
        title = _exchange_diary_result_field(raw, "标题", 80)
        diary_time = _exchange_diary_result_field(raw, "时间", 60)
        detail = f"查看了交换日记{f'《{title}》' if title else ''}"
        if diary_time:
            detail += f"（{diary_time}）"
        elif entry_id:
            detail += f"（{entry_id}）"
        body, comments = _exchange_diary_read_preview(raw)
        return f"{detail}：{body}；评论：{comments}"

    if action == "comment":
        replied = raw.startswith("已回复交换日记评论：")
        if not replied and not raw.startswith("已评论交换日记："):
            return f"交换日记评论未完成{f'（{entry_id}）' if entry_id else ''}"
        comment_count = _exchange_diary_result_field(raw, "评论数", 20)
        detail = "回复了交换日记评论" if replied else "评论了交换日记"
        if entry_id:
            detail += f"（{entry_id}）"
        if comment_count:
            detail += f"；现有{comment_count}条评论"
        return detail

    return "处理了交换日记"


def _generic_detail(name: str, arguments: dict, raw_result: Any, data: dict) -> str:
    if data and not data.get("ok", True):
        return _failure_detail(data)
    for key in ("message", "text", "result", "summary", "content", "time", "datetime"):
        value = data.get(key) if data else None
        if isinstance(value, (str, int, float)) and _text(value):
            return _text(value, 500)
    item = data.get("item") if data and isinstance(data.get("item"), dict) else {}
    if item:
        return _item_label(item)
    if data:
        ignored = {
            "ok", "id", "tool", "source", "meta", "arguments", "content_items", "structured_content",
            "created_at", "updated_at", "expires_at", "window_id", "save_id", "game_id",
        }
        parts: list[str] = []
        for key, value in data.items():
            if key in ignored or isinstance(value, (dict, list)):
                continue
            clean = _text(value, 120)
            if clean:
                parts.append(f"{key}：{clean}")
            if len(parts) >= 4:
                break
        if parts:
            return "；".join(parts)
    raw = _text(raw_result, 500)
    return raw if raw and not raw.startswith(("{", "[")) else "已完成"


def summarize_tool_result(
    name: str,
    arguments: dict | None,
    result: Any,
) -> str:
    tool_name = _text(name, 120) or "unknown_tool"
    args = arguments if isinstance(arguments, dict) else {}
    data = _dict(result)
    if tool_name == "secret_drawer":
        detail = _secret_drawer_detail(args, data)
    elif tool_name in {
        "exchange_diary",
        "exchange_diary_create",
        "exchange_diary_list",
        "exchange_diary_read",
        "exchange_diary_comment_create",
    }:
        detail = _exchange_diary_detail(tool_name, args, result)
    elif tool_name == "galatea_garden":
        detail = _galatea_garden_detail(args, result, data)
    elif tool_name in {"forum_read_feed", "forum_open_thread", "cli", "get_guide"} or tool_name.startswith("forum_"):
        detail = _forum_detail(tool_name, args, data)
    elif tool_name == "web_search":
        detail = _web_search_detail(args, data)
    elif tool_name == "search_memory":
        detail = _memory_search_detail(args, data)
    elif tool_name in _GAME_LOOP_SUMMARY_TOOLS or data.get("game_tool_loop") is True or (data.get("game_id") and data.get("skip_dynamic_memory_write")):
        detail = _game_detail(tool_name, args, data)
    else:
        detail = _generic_detail(tool_name, args, result, data)
    detail = _text(detail, 800).strip()
    return f"使用 {tool_name} 结果：{detail or '未返回可读结果'}"


def _entry_id(tool_call_id: str, tool_name: str, window_id: str) -> str:
    raw = str(tool_call_id or "").strip()
    digest = hashlib.sha256(f"{window_id}\n{tool_name}\n{raw}".encode("utf-8")).hexdigest()
    return f"tool_{digest}"


def _stable_tool_call_id(entry: dict) -> str:
    tool_call_id = str(entry.get("tool_call_id") or "").strip()
    if tool_call_id:
        return tool_call_id
    fallback_raw = json.dumps(
        [entry.get("name"), entry.get("arguments"), entry.get("result")],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return f"missing-id:{hashlib.sha256(fallback_raw.encode('utf-8')).hexdigest()}"


def _prompt_line_chars(summary: str) -> int:
    return len(f"【00:00 {summary}】")


def _prompt_line(row: Any) -> str:
    try:
        label = datetime.fromtimestamp(float(row["created_at"]), tz=_BEIJING).strftime("%H:%M")
    except Exception:
        label = "--:--"
    summary = _text(row["summary"], 900)
    return f"【{label} {summary}】" if summary else ""


def _prune(conn, now: float) -> None:
    conn.execute("DELETE FROM tool_result_cache WHERE expires_at <= ?", (now,))
    rows = conn.execute(
        "SELECT id, summary FROM tool_result_cache ORDER BY created_at ASC, id ASC"
    ).fetchall()
    sizes = {
        str(row["id"]): _prompt_line_chars(_text(row["summary"], 900))
        for row in rows
    }
    total = len(_PROMPT_HEADER) + sum(sizes.values())
    if total <= TOOL_RESULT_CACHE_MAX_CHARS:
        return
    remove_ids: list[str] = []
    for row in rows:
        if total <= TOOL_RESULT_CACHE_TRIM_TO_CHARS:
            break
        entry_id = str(row["id"])
        remove_ids.append(entry_id)
        total -= sizes.get(entry_id, 0)
    if remove_ids:
        conn.executemany("DELETE FROM tool_result_cache WHERE id = ?", [(value,) for value in remove_ids])


def _write_prepared(
    prepared: list[tuple[str, str, str]],
    *,
    window_id: str = "",
    reply_channel: str = "",
) -> int:
    if not prepared:
        return 0

    now = time.time()
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            inserted = 0
            for index, (entry_id, name, summary) in enumerate(prepared):
                inserted += int(
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO tool_result_cache(
                            id, tool_name, summary, window_id, reply_channel, created_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry_id,
                            name,
                            summary,
                            str(window_id or ""),
                            str(reply_channel or ""),
                            now + index * 0.000001,
                            now + TOOL_RESULT_CACHE_TTL_SECONDS,
                        ),
                    ).rowcount
                    > 0
                )
            _prune(conn, now)
            conn.execute("COMMIT")
        return inserted
    except Exception:
        logger.warning("tool_result_cache loop record failed entries=%s", len(prepared), exc_info=True)
        return 0


def _is_game_tool_loop_summary_candidate(entries: list[dict]) -> bool:
    return any(
        isinstance(entry, dict)
        and str(entry.get("name") or "").strip() in _GAME_LOOP_SUMMARY_TOOLS
        for entry in entries or []
    )


def _split_game_tool_loop_entries(entries: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    game_groups_by_name: dict[str, list[dict]] = {}
    passthrough: list[dict] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("name") or "").strip()
        if tool_name in _GAME_LOOP_SUMMARY_TOOLS:
            game_groups_by_name.setdefault(tool_name, []).append(entry)
        else:
            passthrough.append(entry)
    return list(game_groups_by_name.values()), passthrough


def _json_record_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _game_loop_summary_user_prompt(tool_name: str, entries: list[dict]) -> str:
    records = [
        {
            "tool_call_id": str(entry.get("tool_call_id") or ""),
            "arguments": _json_record_value(entry.get("arguments")),
            "result": _json_record_value(entry.get("result")),
        }
        for entry in entries
    ]
    records_json = json.dumps(records, ensure_ascii=False, indent=2, default=str)
    return (
        f"工具名称：{tool_name}\n\n"
        f"以下记录已按实际调用顺序排列：\n{records_json}\n\n"
        "请将以上连续调用融合成一条历史摘要。"
    )


def _request_game_tool_loop_summary(tool_name: str, entries: list[dict]) -> str:
    api_key = resolve_siliconflow_api_key()
    if not api_key:
        raise RuntimeError("SiliconFlow API key 未配置")

    response = requests.post(
        f"https://{SILICONFLOW_BASE_HOST}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _GAME_LOOP_SUMMARY_MODEL,
            "messages": [
                {"role": "system", "content": _GAME_LOOP_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": _game_loop_summary_user_prompt(tool_name, entries)},
            ],
            "stream": False,
            "enable_thinking": False,
            "temperature": 0.1,
            "response_format": {"type": "text"},
        },
        timeout=CHAT_RESPONSE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""
    summary = _text_without_limit(content)
    if not summary:
        raise ValueError("SiliconFlow 返回空摘要")
    return summary


def _record_game_tool_loop_summary(
    entries: list[dict],
    *,
    window_id: str = "",
    reply_channel: str = "",
) -> int:
    tool_name = str(entries[0].get("name") or "").strip()
    try:
        summary = _request_game_tool_loop_summary(tool_name, entries)
    except Exception:
        logger.warning(
            "游戏工具整轮模型摘要失败，回退逐条摘要 tool=%s calls=%s",
            tool_name,
            len(entries),
            exc_info=True,
        )
        return record_tool_loop(entries, window_id=window_id, reply_channel=reply_channel)

    ordered_call_ids = [_stable_tool_call_id(entry) for entry in entries]
    fingerprint = hashlib.sha256(
        json.dumps(ordered_call_ids, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    merged_call_id = f"game-loop:{fingerprint}"
    inserted = _write_prepared(
        [
            (
                _entry_id(merged_call_id, tool_name, str(window_id or "")),
                tool_name,
                f"使用 {tool_name} 连续结果：{summary}",
            )
        ],
        window_id=window_id,
        reply_channel=reply_channel,
    )
    logger.info(
        "游戏工具整轮模型摘要写入 tool=%s calls=%s inserted=%s",
        tool_name,
        len(entries),
        inserted,
    )
    return inserted


def _game_loop_summary_worker() -> None:
    while True:
        entries, window_id, reply_channel = _GAME_LOOP_SUMMARY_QUEUE.get()
        try:
            _record_game_tool_loop_summary(
                entries,
                window_id=window_id,
                reply_channel=reply_channel,
            )
        except Exception:
            logger.exception("游戏工具整轮摘要后台任务异常")
        finally:
            _GAME_LOOP_SUMMARY_QUEUE.task_done()


def _ensure_game_loop_summary_worker() -> None:
    global _GAME_LOOP_SUMMARY_THREAD
    with _GAME_LOOP_SUMMARY_THREAD_LOCK:
        if _GAME_LOOP_SUMMARY_THREAD is not None and _GAME_LOOP_SUMMARY_THREAD.is_alive():
            return
        _GAME_LOOP_SUMMARY_THREAD = threading.Thread(
            target=_game_loop_summary_worker,
            name="game-tool-loop-summary",
            daemon=True,
        )
        _GAME_LOOP_SUMMARY_THREAD.start()


def enqueue_game_tool_loop_summary(
    entries: list[dict],
    *,
    window_id: str = "",
    reply_channel: str = "",
) -> bool:
    game_groups, passthrough = _split_game_tool_loop_entries(entries)
    if not game_groups:
        return False
    if passthrough:
        record_tool_loop(
            passthrough,
            window_id=window_id,
            reply_channel=reply_channel,
        )
    _ensure_game_loop_summary_worker()
    for group in game_groups:
        _GAME_LOOP_SUMMARY_QUEUE.put(
            (
                copy.deepcopy(group),
                str(window_id or ""),
                str(reply_channel or ""),
            )
        )
    return True


def record_tool_loop(
    entries: list[dict],
    *,
    window_id: str = "",
    reply_channel: str = "",
) -> int:
    """Write one completed tool loop atomically so its internal rounds keep a stable prompt prefix."""
    prepared: list[tuple[str, str, str]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        summary = summarize_tool_result(name, entry.get("arguments"), entry.get("result"))
        if not summary:
            continue
        tool_call_id = _stable_tool_call_id(entry)
        prepared.append(
            (
                _entry_id(tool_call_id, name, str(window_id or "")),
                name,
                summary,
            )
        )
    if not prepared:
        return 0
    return _write_prepared(prepared, window_id=window_id, reply_channel=reply_channel)


def record_tool_result(
    *,
    tool_call_id: str,
    name: str,
    arguments: dict | None,
    result: Any,
    window_id: str = "",
    reply_channel: str = "",
) -> bool:
    return bool(
        record_tool_loop(
            [
                {
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "arguments": arguments,
                    "result": result,
                }
            ],
            window_id=window_id,
            reply_channel=reply_channel,
        )
    )


def list_prompt_lines() -> list[str]:
    now = time.time()
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _prune(conn, now)
            rows = conn.execute(
                "SELECT summary, created_at FROM tool_result_cache ORDER BY created_at ASC, id ASC"
            ).fetchall()
            conn.execute("COMMIT")
    except Exception:
        logger.warning("tool_result_cache read failed", exc_info=True)
        return []
    return [line for row in rows if (line := _prompt_line(row))]


def prompt_system_contents() -> list[str]:
    return [_PROMPT_HEADER, *list_prompt_lines()]


def prompt_generation_contents(*, window_id: str, generation_id: int) -> dict:
    """Return one generation-frozen tool block and the post-cutoff hot blocks."""
    normalized_window_id = str(window_id or "")
    normalized_generation_id = int(generation_id or 0)
    now = time.time()
    snapshot_created = False
    snapshot_reason = ""
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _prune(conn, now)
            generation_row = conn.execute(
                """
                SELECT generation_id, frozen_text, cutoff_created_at
                FROM prompt_tool_generation
                WHERE window_id = ?
                """,
                (normalized_window_id,),
            ).fetchone()
            if generation_row is None or int(generation_row["generation_id"]) != normalized_generation_id:
                snapshot_rows = conn.execute(
                    """
                    SELECT id, summary, created_at
                    FROM tool_result_cache
                    ORDER BY created_at ASC, id ASC
                    """
                ).fetchall()
                snapshot_lines = [line for row in snapshot_rows if (line := _prompt_line(row))]
                frozen_text = _FROZEN_PROMPT_HEADER
                if snapshot_lines:
                    frozen_text += "\n\n" + "\n".join(snapshot_lines)
                cutoff_created_at = (
                    max(float(row["created_at"]) for row in snapshot_rows)
                    if snapshot_rows
                    else now
                )
                conn.execute(
                    """
                    INSERT INTO prompt_tool_generation(
                        window_id, generation_id, frozen_text, cutoff_created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(window_id) DO UPDATE SET
                        generation_id = excluded.generation_id,
                        frozen_text = excluded.frozen_text,
                        cutoff_created_at = excluded.cutoff_created_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        normalized_window_id,
                        normalized_generation_id,
                        frozen_text,
                        cutoff_created_at,
                        now,
                    ),
                )
                frozen_entries = len(snapshot_lines)
                snapshot_created = True
                snapshot_reason = "memory_generation"
            else:
                frozen_text = str(generation_row["frozen_text"] or "")
                cutoff_created_at = float(generation_row["cutoff_created_at"])
                frozen_entries = 0

            hot_rows_desc = conn.execute(
                """
                SELECT id, summary, created_at
                FROM tool_result_cache
                WHERE created_at > ?
                ORDER BY created_at DESC, id DESC
                """,
                (cutoff_created_at,),
            ).fetchall()
            hot_lines_asc = [
                line
                for row in reversed(hot_rows_desc)
                if (line := _prompt_line(row))
            ]
            complete_hot_chars = (
                len(_HOT_PROMPT_HEADER) + 2 + sum(len(line) for line in hot_lines_asc)
                if hot_lines_asc
                else 0
            )
            if not snapshot_created and complete_hot_chars > TOOL_RESULT_HOT_MAX_CHARS:
                snapshot_rows = conn.execute(
                    """
                    SELECT id, summary, created_at
                    FROM tool_result_cache
                    ORDER BY created_at ASC, id ASC
                    """
                ).fetchall()
                snapshot_lines = [line for row in snapshot_rows if (line := _prompt_line(row))]
                frozen_text = _FROZEN_PROMPT_HEADER
                if snapshot_lines:
                    frozen_text += "\n\n" + "\n".join(snapshot_lines)
                cutoff_created_at = (
                    max(float(row["created_at"]) for row in snapshot_rows)
                    if snapshot_rows
                    else now
                )
                conn.execute(
                    """
                    UPDATE prompt_tool_generation
                    SET frozen_text = ?, cutoff_created_at = ?, updated_at = ?
                    WHERE window_id = ? AND generation_id = ?
                    """,
                    (
                        frozen_text,
                        cutoff_created_at,
                        now,
                        normalized_window_id,
                        normalized_generation_id,
                    ),
                )
                frozen_entries = len(snapshot_lines)
                snapshot_created = True
                snapshot_reason = "hot_overflow"
                hot_rows_desc = []
            conn.execute("COMMIT")
    except Exception:
        logger.warning(
            "tool generation prompt read failed window_id=%s generation_id=%s",
            normalized_window_id,
            normalized_generation_id,
            exc_info=True,
        )
        return {
            "frozen_text": "",
            "hot_blocks": [],
            "cutoff_created_at": 0.0,
            "frozen_entries": 0,
            "hot_entries": 0,
            "hot_chars": 0,
        }

    if snapshot_created:
        logger.info(
            "tool_generation_snapshot window_id=%s generation_id=%s reason=%s frozen_entries=%s frozen_chars=%s cutoff_created_at=%s",
            normalized_window_id,
            normalized_generation_id,
            snapshot_reason,
            frozen_entries,
            len(frozen_text),
            cutoff_created_at,
        )

    hot_blocks = [line for row in reversed(hot_rows_desc) if (line := _prompt_line(row))]
    if hot_blocks:
        hot_blocks[0] = _HOT_PROMPT_HEADER + "\n\n" + hot_blocks[0]
        hot_chars = sum(len(block) for block in hot_blocks)
    else:
        hot_chars = 0
    return {
        "frozen_text": frozen_text,
        "hot_blocks": hot_blocks,
        "cutoff_created_at": cutoff_created_at,
        "frozen_entries": frozen_entries,
        "hot_entries": len(hot_blocks),
        "hot_chars": hot_chars,
    }
