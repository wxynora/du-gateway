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
    TOOL_RESULT_CACHE_MAX_CHARS,
    TOOL_RESULT_CACHE_TRIM_TO_CHARS,
    TOOL_RESULT_CACHE_TTL_SECONDS,
    TOOL_RESULT_HOT_MAX_CHARS,
)
from services.worker_models import get_worker_model
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
_RECENT_TOOL_BATCH_HEADER = "〖本段工具摘要〗"
_GAME_LOOP_SUMMARY_TOOLS = frozenset({"random_imitator_td", "farm", "cedareco", "travel"})
_FARM_READ_ONLY_ACTIONS = frozenset(
    {
        "bag",
        "encyclopedia",
        "expedition",
        "help",
        "leaderboard",
        "ledger",
        "market",
        "shop",
        "status",
    }
)
_FARM_TRAILING_PANEL_PREFIXES = (
    "🌾 你站在",
    "🌟 流光时刻：",
    "🏪 商店：",
    "🎯 任务：",
    "🎈 小贴士：",
    "📣 此刻谁家菜熟了：",
    "🥷 你今天已偷过：",
)
_GAME_LOOP_SUMMARY_SYSTEM_PROMPT = """你负责把同一轮单机游戏中的连续工具调用记录融合成一条准确、自然的中文历史摘要。

严格按照记录顺序整理，只写记录中实际发生的内容。
保留实际执行的动作、关键状态变化、资源获得或消耗、失败原因和终局结果；相同状态只合并表达一次，不得遗漏会影响后续游戏判断的信息。
忽略每次结果中重复出现的游戏规则、操作方法、命令说明、字段说明、固定 system/guide、协议标记、界面标题和其他不会随本轮操作变化的固定文字。只有某条规则在本轮发生变化，或实际触发并直接影响本轮结果时，才保留与该结果有关的部分。
不得编造、推测或评价操作，不要使用第一人称或第二人称。
只输出一条完整正文，不输出标题、列表、Markdown、JSON、解释或前后缀。"""
_GAME_LOOP_SUMMARY_QUEUE: queue.Queue = queue.Queue()
_GAME_LOOP_SUMMARY_THREAD: threading.Thread | None = None
_GAME_LOOP_SUMMARY_THREAD_LOCK = threading.Lock()
_GAME_LOOP_SUMMARY_PENDING = threading.Condition()
_GAME_LOOP_SUMMARY_PENDING_TASKS: set[str] = set()


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


def _public_repo_detail(arguments: dict, data: dict) -> str:
    action = _text(data.get("action") or arguments.get("action"), 40)
    repo = _text(data.get("repo") or arguments.get("repo"), 180)
    if not data.get("ok", True):
        target = f"{repo} {action}".strip()
        return f"查看公共仓库{f' {target}' if target else ''}失败：{_failure_detail(data)}"

    resolved_sha = _text(data.get("resolved_sha"), 40)
    sha_label = resolved_sha[:12] if resolved_sha else ""
    path = _text(data.get("path") or arguments.get("path"), 240)
    query = _text(data.get("query") or arguments.get("query"), 160)
    locator = f"{repo}{f'@{sha_label}' if sha_label else ''}"
    if action == "overview":
        return f"查看了公共仓库 {locator} 的概览"
    if action == "list":
        entries = data.get("entries") if isinstance(data.get("entries"), list) else []
        return f"列出了公共仓库 {locator} 的目录 {path or '/'}，本页 {len(entries)} 项"
    if action == "read":
        line_range = data.get("line_range") if isinstance(data.get("line_range"), dict) else {}
        start = _text(line_range.get("start"), 20)
        end = _text(line_range.get("end"), 20)
        lines = f"第{start}-{end}行" if start and end else "指定区间"
        return f"读取了公共仓库 {locator} 的 {path or '文件'}（{lines}）"
    if action in {"search_path", "search_code"}:
        matches = data.get("matches") if isinstance(data.get("matches"), list) else []
        label = "路径" if action == "search_path" else "代码"
        if action == "search_code":
            followup = f"；后续读取基准为 @{sha_label}" if sha_label else ""
            return f"在公共仓库 {repo} 搜索{label}“{query}”，本页 {len(matches)} 项{followup}"
        return f"在公共仓库 {locator} 搜索{label}“{query}”，本页 {len(matches)} 项"
    return f"查看了公共仓库 {locator}"


def _farm_entry_arguments(entry: dict) -> dict:
    function = entry.get("function") if isinstance(entry.get("function"), dict) else {}
    raw = entry.get("arguments")
    if raw in (None, ""):
        raw = function.get("arguments")
    return _dict(raw)


def _farm_result_text(entry: dict) -> tuple[str, bool]:
    raw_result = entry.get("result")
    data = _dict(raw_result)
    is_error = data.get("isError") is True or data.get("ok") is False
    texts: list[str] = []
    content = data.get("content") if isinstance(data.get("content"), list) else []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            texts.append(text)
    if not texts:
        fallback = data.get("text") or data.get("result") or data.get("message")
        if fallback:
            texts.append(str(fallback).strip())
        elif isinstance(raw_result, str) and not data:
            texts.append(raw_result.strip())
    return "\n".join(text for text in texts if text).strip(), is_error


def _farm_is_read_only(arguments: dict) -> bool:
    action = str(arguments.get("action") or "").strip().lower()
    if action in _FARM_READ_ONLY_ACTIONS:
        return True
    if action == "kitchen":
        return not str(arguments.get("op") or "").strip()
    if action == "glimmer":
        return not str(arguments.get("op") or "").strip()
    if action == "fish":
        return bool(arguments.get("view")) and not any(
            key in arguments for key in ("buy", "leave", "open", "sell", "times")
        )
    if action == "guestbook":
        return "on" not in arguments
    if action == "together":
        return not str(arguments.get("option") or "").strip()
    return False


def _farm_action_label(arguments: dict) -> str:
    action = str(arguments.get("action") or "").strip().lower()
    if action == "kitchen":
        op = str(arguments.get("op") or "").strip().lower()
        if op == "cook":
            return f"制作{_text_without_limit(arguments.get('recipe') or '料理')}"
        if op == "buy":
            kind = "食谱" if str(arguments.get("kind") or "").strip().lower() == "recipe" else "食材"
            return f"购买{kind}"
        if op == "use":
            return f"使用料理{_text_without_limit(arguments.get('dishId'))}"
        if op == "sell":
            return f"出售{_text_without_limit(arguments.get('itemId'))}"
        return f"料理台{op or '操作'}"
    if action == "glimmer" and str(arguments.get("op") or "").strip().lower() == "catch":
        animal = _text_without_limit(arguments.get("animal"))
        dish = _text_without_limit(arguments.get("dish"))
        return f"用{dish}诱捕{animal}" if dish and animal else "诱捕异色动物"
    if action == "use":
        item = _text_without_limit(arguments.get("item"))
        if item == "speed_potion":
            return "使用加速药水"
        return f"使用{item}" if item else "使用物品"
    return {
        "harvest": "收获",
        "plant": "种植",
        "run": "完成一轮农活",
        "water": "浇水",
    }.get(action, action or "农场操作")


def _farm_read_only_summary(arguments: dict) -> str:
    action = str(arguments.get("action") or "").strip().lower()
    if action == "kitchen":
        return "查看了已解锁食谱" if arguments.get("view") == "recipes" else "查看了料理台"
    if action == "fish":
        view = _text_without_limit(arguments.get("view"))
        return f"查看了钓鱼{view}" if view else "查看了钓鱼状态"
    if action == "glimmer":
        return "查看了流光原野"
    if action == "guestbook":
        return "查看了留言板"
    if action == "together":
        return "查看了铃野共行完整前情" if arguments.get("view") == "history" else "查看了铃野共行当前剧情"
    if action == "encyclopedia":
        item_id = _text_without_limit(arguments.get("id"))
        return f"查看了图鉴{item_id}" if item_id else "查看了图鉴"
    return {
        "bag": "查看了素材库",
        "expedition": "查看了探险进度",
        "help": "查看了农场帮助",
        "leaderboard": "查看了排行榜",
        "ledger": "查看了账本",
        "market": "查看了自己的摊位",
        "shop": "查看了商店",
        "status": "查看了农场状态",
    }.get(action, f"查看了{action or '农场状态'}")


def _farm_operation_result(raw_text: str, arguments: dict) -> str:
    action = str(arguments.get("action") or "").strip().lower()
    lines: list[str] = []
    for raw_line in str(raw_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        is_farm_status = bool(re.match(r"^🌾【[^】]+】熟\d+·长\d+·空\d+", line))
        is_action_panel = any(
            line.startswith(prefix) and (action != owner or bool(lines))
            for prefix, owner in (
                ("🎣 月光池塘", "fish"),
                ("✨ 流光原野开放中", "glimmer"),
                ("🧭 铃野共行：", "together"),
            )
        )
        if (
            is_farm_status
            or is_action_panel
            or line.startswith(_FARM_TRAILING_PANEL_PREFIXES)
            or line.startswith('{"farm":')
        ):
            break
        lines.append(line)

    if action == "plant":
        for line in lines:
            if "种下" in line and line.startswith(("（", "(")):
                return _text_without_limit(line)
    return _text_without_limit(" ".join(lines))


def _summarize_farm_tool_loop(entries: list[dict]) -> str:
    changes: list[str] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        arguments = _farm_entry_arguments(entry)
        if _farm_is_read_only(arguments):
            changes.append(_farm_read_only_summary(arguments))
            continue
        raw_text, is_error = _farm_result_text(entry)
        outcome = _farm_operation_result(raw_text, arguments)
        label = _farm_action_label(arguments)
        if is_error:
            changes.append(f"{label}失败：{outcome or '工具未返回错误详情'}")
        elif outcome:
            changes.append(f"{label}：{outcome}")
        else:
            changes.append(f"尝试{label}，工具未返回可读结果")
    return "；".join(changes)


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
    elif tool_name == "public_repo":
        detail = _public_repo_detail(args, data)
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
    tool_call_id = str(entry.get("tool_call_id") or entry.get("id") or "").strip()
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


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _append_hot_items_to_prompt_generations(
    conn,
    items: list[dict],
    now: float,
    *,
    window_id: str,
) -> None:
    if not items:
        return
    rows = conn.execute(
        """
        SELECT window_id, hot_items_json
        FROM prompt_tool_generation
        WHERE lifecycle_mode = 'rolling' AND window_id = ?
        """,
        (str(window_id or ""),),
    ).fetchall()
    for row in rows:
        current = [item for item in _json_list(row["hot_items_json"]) if isinstance(item, dict)]
        existing_ids = {str(item.get("id") or "") for item in current}
        changed = False
        for item in items:
            item_id = str(item.get("id") or "")
            if not item_id or item_id in existing_ids:
                continue
            current.append(dict(item))
            existing_ids.add(item_id)
            changed = True
        if changed:
            conn.execute(
                """
                UPDATE prompt_tool_generation
                SET hot_items_json = ?, updated_at = ?
                WHERE window_id = ? AND lifecycle_mode = 'rolling'
                """,
                (json.dumps(current, ensure_ascii=False), now, str(row["window_id"])),
            )


def _remove_hot_items_from_prompt_generations(conn, item_ids: set[str], now: float) -> None:
    if not item_ids:
        return
    rows = conn.execute(
        """
        SELECT window_id, hot_items_json
        FROM prompt_tool_generation
        WHERE lifecycle_mode = 'rolling'
        """
    ).fetchall()
    for row in rows:
        current = [item for item in _json_list(row["hot_items_json"]) if isinstance(item, dict)]
        retained = [item for item in current if str(item.get("id") or "") not in item_ids]
        if len(retained) == len(current):
            continue
        conn.execute(
            """
            UPDATE prompt_tool_generation
            SET hot_items_json = ?, updated_at = ?
            WHERE window_id = ? AND lifecycle_mode = 'rolling'
            """,
            (json.dumps(retained, ensure_ascii=False), now, str(row["window_id"])),
        )


def _prune(conn, now: float) -> None:
    removed_ids = {
        str(row["id"])
        for row in conn.execute(
            "SELECT id FROM tool_result_cache WHERE expires_at <= ?",
            (now,),
        ).fetchall()
    }
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
        _remove_hot_items_from_prompt_generations(conn, removed_ids, now)
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
        removed_ids.update(remove_ids)
    _remove_hot_items_from_prompt_generations(conn, removed_ids, now)


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
            inserted_hot_items: list[dict] = []
            for index, (entry_id, name, summary) in enumerate(prepared):
                created_at = now + index * 0.000001
                was_inserted = bool(
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
                            created_at,
                            now + TOOL_RESULT_CACHE_TTL_SECONDS,
                        ),
                    ).rowcount > 0
                )
                inserted += int(was_inserted)
                if was_inserted:
                    text = _prompt_line({"summary": summary, "created_at": created_at})
                    if text:
                        inserted_hot_items.append({"id": entry_id, "text": text})
            _append_hot_items_to_prompt_generations(
                conn,
                inserted_hot_items,
                now,
                window_id=str(window_id or ""),
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
        and _tool_entry_name(entry) in _GAME_LOOP_SUMMARY_TOOLS
        for entry in entries or []
    )


def _tool_entry_name(entry: dict) -> str:
    function = entry.get("function") if isinstance(entry.get("function"), dict) else {}
    return str(entry.get("name") or function.get("name") or "").strip()


def _split_game_tool_loop_entries(entries: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    game_groups_by_name: dict[str, list[dict]] = {}
    passthrough: list[dict] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        tool_name = _tool_entry_name(entry)
        if tool_name in _GAME_LOOP_SUMMARY_TOOLS:
            game_groups_by_name.setdefault(tool_name, []).append(entry)
        else:
            passthrough.append(entry)
    return list(game_groups_by_name.values()), passthrough


def _game_loop_summary_task_key(entries: list[dict], *, window_id: str) -> str:
    ordered_call_ids = [_stable_tool_call_id(entry) for entry in entries]
    fingerprint = hashlib.sha256(
        json.dumps(ordered_call_ids, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"{str(window_id or '')}:{fingerprint}"


def _register_game_loop_summary_task(task_key: str) -> None:
    if not task_key:
        return
    with _GAME_LOOP_SUMMARY_PENDING:
        _GAME_LOOP_SUMMARY_PENDING_TASKS.add(task_key)


def _finish_game_loop_summary_task(task_key: str) -> None:
    if not task_key:
        return
    with _GAME_LOOP_SUMMARY_PENDING:
        _GAME_LOOP_SUMMARY_PENDING_TASKS.discard(task_key)
        _GAME_LOOP_SUMMARY_PENDING.notify_all()


def _tool_entries_for_archived_round(round_item: dict) -> list[dict]:
    messages = round_item.get("messages") if isinstance(round_item.get("messages"), list) else []
    round_entries: list[dict] = []
    for message in messages:
        if not isinstance(message, dict) or str(message.get("role") or "").strip().lower() != "assistant":
            continue
        tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
        round_entries.extend(item for item in tool_calls if isinstance(item, dict))
    return round_entries


def _game_loop_summary_task_keys_for_rounds(rounds: list[dict], *, window_id: str) -> list[str]:
    task_keys: list[str] = []
    seen: set[str] = set()
    for round_item in rounds or []:
        if not isinstance(round_item, dict):
            continue
        round_entries = _tool_entries_for_archived_round(round_item)
        game_groups, _passthrough = _split_game_tool_loop_entries(round_entries)
        for group in game_groups:
            task_key = _game_loop_summary_task_key(group, window_id=window_id)
            if task_key and task_key not in seen:
                seen.add(task_key)
                task_keys.append(task_key)
    return task_keys


def tool_cache_item_ids_for_rounds(rounds: list[dict], *, window_id: str) -> list[str]:
    """Return every possible cache row id produced by the archived tool calls in these rounds."""
    item_ids: list[str] = []
    seen: set[str] = set()

    def _append(item_id: str) -> None:
        if item_id and item_id not in seen:
            seen.add(item_id)
            item_ids.append(item_id)

    for round_item in rounds or []:
        if not isinstance(round_item, dict):
            continue
        game_groups, passthrough = _split_game_tool_loop_entries(
            _tool_entries_for_archived_round(round_item)
        )
        for group in game_groups:
            tool_name = _tool_entry_name(group[0])
            fingerprint = _game_loop_summary_task_key(group, window_id=window_id).rsplit(":", 1)[-1]
            _append(_entry_id(f"game-loop:{fingerprint}", tool_name, str(window_id or "")))
            for entry in group:
                _append(
                    _entry_id(
                        _stable_tool_call_id(entry),
                        tool_name,
                        str(window_id or ""),
                    )
                )
        for entry in passthrough:
            tool_name = _tool_entry_name(entry)
            _append(
                _entry_id(
                    _stable_tool_call_id(entry),
                    tool_name,
                    str(window_id or ""),
                )
            )
    return item_ids


def wait_for_game_tool_loop_summaries(rounds: list[dict], *, window_id: str) -> int:
    """Wait until async game summaries referenced by these archived rounds reach terminal write handling."""
    task_keys = _game_loop_summary_task_keys_for_rounds(rounds, window_id=window_id)
    if not task_keys:
        return 0
    expected = set(task_keys)
    with _GAME_LOOP_SUMMARY_PENDING:
        pending = expected.intersection(_GAME_LOOP_SUMMARY_PENDING_TASKS)
        if pending:
            logger.info(
                "近期总结等待对应异步工具摘要 window_id=%s tasks=%s",
                window_id,
                len(pending),
            )
        while expected.intersection(_GAME_LOOP_SUMMARY_PENDING_TASKS):
            _GAME_LOOP_SUMMARY_PENDING.wait()
    return len(task_keys)


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
    worker = get_worker_model("structured")
    if not worker.api_key:
        raise RuntimeError("SiliconFlow API key 未配置")

    response = requests.post(
        worker.api_url,
        headers={
            "Authorization": f"Bearer {worker.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": worker.model,
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
    tool_name = _tool_entry_name(entries[0])
    if tool_name == "farm":
        summary = _summarize_farm_tool_loop(entries)
        if not summary:
            logger.info("农场工具整轮无可摘要调用，跳过摘要 calls=%s", len(entries))
            return 0
    else:
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

    task_key = _game_loop_summary_task_key(entries, window_id=window_id)
    fingerprint = task_key.rsplit(":", 1)[-1]
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
        "游戏工具整轮摘要写入 tool=%s calls=%s inserted=%s mode=%s",
        tool_name,
        len(entries),
        inserted,
        "deterministic" if tool_name == "farm" else "model",
    )
    return inserted


def _game_loop_summary_worker() -> None:
    while True:
        entries, window_id, reply_channel, task_key = _GAME_LOOP_SUMMARY_QUEUE.get()
        try:
            _record_game_tool_loop_summary(
                entries,
                window_id=window_id,
                reply_channel=reply_channel,
            )
        except Exception:
            logger.exception("游戏工具整轮摘要后台任务异常")
        finally:
            _finish_game_loop_summary_task(task_key)
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
        task_key = _game_loop_summary_task_key(group, window_id=str(window_id or ""))
        _register_game_loop_summary_task(task_key)
        _GAME_LOOP_SUMMARY_QUEUE.put(
            (
                copy.deepcopy(group),
                str(window_id or ""),
                str(reply_channel or ""),
                task_key,
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


def _snapshot_text(rows: list[Any]) -> tuple[str, int]:
    lines = [line for row in rows if (line := _prompt_line(row))]
    text = _FROZEN_PROMPT_HEADER
    if lines:
        text += "\n\n" + "\n".join(lines)
    return text, len(lines)


def _recent_tool_batch(items: list[dict], *, chunk_index: int, summary_chunk_id: str) -> dict | None:
    lines = [str(item.get("text") or "").strip() for item in items if isinstance(item, dict)]
    lines = [line for line in lines if line]
    if not lines:
        return None
    return {
        "chunk_index": int(chunk_index),
        "summary_chunk_id": str(summary_chunk_id or ""),
        "item_ids": [str(item.get("id") or "") for item in items if str(item.get("id") or "")],
        "text": _RECENT_TOOL_BATCH_HEADER + "\n" + "\n".join(f"- {line}" for line in lines),
    }


def _normalized_chunk_ids(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        chunk_id = str(value or "").strip()
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        out.append(chunk_id)
    return out


def _normalized_chunk_item_ids(values: Any) -> dict[str, set[str]]:
    if not isinstance(values, dict):
        return {}
    out: dict[str, set[str]] = {}
    for raw_chunk_id, raw_item_ids in values.items():
        chunk_id = str(raw_chunk_id or "").strip()
        if not chunk_id:
            continue
        out[chunk_id] = {
            str(item_id).strip()
            for item_id in raw_item_ids or []
            if str(item_id or "").strip()
        }
    return out


def _seal_missing_tool_chunks(
    *,
    generation_id: int,
    chunk_ids: list[str],
    current_chunk_index: int,
    sealed_chunk_ids: list[str],
    hot_items: list[dict],
    recent_tool_batches: list[dict],
    chunk_item_ids: dict[str, set[str]] | None = None,
) -> tuple[int, list[str], list[dict], list[dict], list[tuple[int, int, str, int, int]]]:
    missing_chunk_ids = [
        chunk_id for chunk_id in chunk_ids
        if chunk_id not in set(sealed_chunk_ids)
    ]
    sealed_logs: list[tuple[int, int, str, int, int]] = []
    configured_item_ids = chunk_item_ids or {}
    for chunk_id in missing_chunk_ids:
        current_chunk_index += 1
        if chunk_id in configured_item_ids:
            selected_ids = configured_item_ids[chunk_id]
            batch_items = [
                item for item in hot_items
                if str(item.get("id") or "") in selected_ids
            ]
            hot_items = [
                item for item in hot_items
                if str(item.get("id") or "") not in selected_ids
            ]
        else:
            batch_items = hot_items
            hot_items = []
        batch = _recent_tool_batch(
            batch_items,
            chunk_index=current_chunk_index,
            summary_chunk_id=chunk_id,
        )
        if batch is not None:
            recent_tool_batches.append(batch)
        sealed_logs.append(
            (
                int(generation_id or 0),
                current_chunk_index,
                chunk_id,
                len(batch_items),
                len(str(batch.get("text") or "")) if batch else 0,
            )
        )
        sealed_chunk_ids.append(chunk_id)
    return (
        current_chunk_index,
        sealed_chunk_ids,
        hot_items,
        recent_tool_batches,
        sealed_logs,
    )


def prompt_generation_contents(
    *,
    window_id: str,
    generation_id: int,
    generation_chunk_ids: list[str] | None = None,
    previous_generation_chunk_ids: list[str] | None = None,
    generation_chunk_item_ids: dict[str, list[str]] | None = None,
) -> dict:
    """Return the immutable stable/recent tool blocks plus the current chunk-window Hot."""
    normalized_window_id = str(window_id or "")
    normalized_generation_id = int(generation_id or 0)
    normalized_chunk_ids = _normalized_chunk_ids(generation_chunk_ids)
    normalized_previous_chunk_ids = _normalized_chunk_ids(previous_generation_chunk_ids)
    normalized_chunk_item_ids = _normalized_chunk_item_ids(generation_chunk_item_ids)
    now = time.time()
    snapshot_created = False
    snapshot_reason = ""
    sealed_logs: list[tuple[int, int, str, int, int]] = []
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _prune(conn, now)
            generation_row = conn.execute(
                """
                SELECT generation_id, frozen_text, cutoff_created_at,
                       lifecycle_mode, current_chunk_index,
                       sealed_chunk_ids_json, hot_items_json,
                       recent_tool_batches_json
                FROM prompt_tool_generation
                WHERE window_id = ?
                """,
                (normalized_window_id,),
            ).fetchone()

            if generation_row is None or int(generation_row["generation_id"]) != normalized_generation_id:
                previous_row_generation_id = (
                    int(generation_row["generation_id"])
                    if generation_row is not None
                    else -1
                )
                carryover_hot_items: list[dict] = []
                if (
                    generation_row is not None
                    and previous_row_generation_id + 1 == normalized_generation_id
                    and str(generation_row["lifecycle_mode"] or "legacy") == "rolling"
                    and normalized_previous_chunk_ids
                ):
                    (
                        _previous_chunk_index,
                        _previous_sealed_chunk_ids,
                        carryover_hot_items,
                        _previous_recent_tool_batches,
                        rollover_sealed_logs,
                    ) = _seal_missing_tool_chunks(
                        generation_id=previous_row_generation_id,
                        chunk_ids=normalized_previous_chunk_ids,
                        current_chunk_index=max(0, int(generation_row["current_chunk_index"] or 0)),
                        sealed_chunk_ids=_normalized_chunk_ids(
                            _json_list(generation_row["sealed_chunk_ids_json"])
                        ),
                        hot_items=[
                            item for item in _json_list(generation_row["hot_items_json"])
                            if isinstance(item, dict)
                        ],
                        recent_tool_batches=[
                            item for item in _json_list(generation_row["recent_tool_batches_json"])
                            if isinstance(item, dict)
                        ],
                        chunk_item_ids=normalized_chunk_item_ids,
                    )
                    sealed_logs.extend(rollover_sealed_logs)
                snapshot_rows = conn.execute(
                    """
                    SELECT id, summary, created_at
                    FROM tool_result_cache
                    ORDER BY created_at ASC, id ASC
                    """
                ).fetchall()
                carryover_item_ids = {
                    str(item.get("id") or "")
                    for item in carryover_hot_items
                    if str(item.get("id") or "")
                }
                if carryover_item_ids:
                    snapshot_rows = [
                        row for row in snapshot_rows
                        if str(row["id"] or "") not in carryover_item_ids
                    ]
                frozen_text, frozen_entries = _snapshot_text(snapshot_rows)
                cutoff_created_at = (
                    max(float(row["created_at"]) for row in snapshot_rows)
                    if snapshot_rows
                    else now
                )
                conn.execute(
                    """
                    INSERT INTO prompt_tool_generation(
                        window_id, generation_id, frozen_text, cutoff_created_at,
                        lifecycle_mode, current_chunk_index, sealed_chunk_ids_json,
                        hot_items_json, recent_tool_batches_json, updated_at
                    ) VALUES (?, ?, ?, ?, 'rolling', ?, ?, ?, '[]', ?)
                    ON CONFLICT(window_id) DO UPDATE SET
                        generation_id = excluded.generation_id,
                        frozen_text = excluded.frozen_text,
                        cutoff_created_at = excluded.cutoff_created_at,
                        lifecycle_mode = 'rolling',
                        current_chunk_index = excluded.current_chunk_index,
                        sealed_chunk_ids_json = excluded.sealed_chunk_ids_json,
                        hot_items_json = excluded.hot_items_json,
                        recent_tool_batches_json = '[]',
                        updated_at = excluded.updated_at
                    """,
                    (
                        normalized_window_id,
                        normalized_generation_id,
                        frozen_text,
                        cutoff_created_at,
                        len(normalized_chunk_ids),
                        json.dumps(normalized_chunk_ids, ensure_ascii=False),
                        json.dumps(carryover_hot_items, ensure_ascii=False),
                        now,
                    ),
                )
                lifecycle_mode = "rolling"
                current_chunk_index = len(normalized_chunk_ids)
                sealed_chunk_ids = list(normalized_chunk_ids)
                hot_items = list(carryover_hot_items)
                recent_tool_batches: list[dict] = []
                snapshot_created = True
                snapshot_reason = (
                    "memory_generation_atomic_rollover"
                    if sealed_logs
                    else "memory_generation"
                )
            else:
                frozen_text = str(generation_row["frozen_text"] or "")
                cutoff_created_at = float(generation_row["cutoff_created_at"])
                frozen_entries = 0
                lifecycle_mode = str(generation_row["lifecycle_mode"] or "legacy")
                current_chunk_index = max(0, int(generation_row["current_chunk_index"] or 0))
                sealed_chunk_ids = _normalized_chunk_ids(_json_list(generation_row["sealed_chunk_ids_json"]))
                hot_items = [
                    item for item in _json_list(generation_row["hot_items_json"])
                    if isinstance(item, dict)
                ]
                recent_tool_batches = [
                    item for item in _json_list(generation_row["recent_tool_batches_json"])
                    if isinstance(item, dict)
                ]

                if lifecycle_mode != "rolling":
                    hot_rows_desc = conn.execute(
                        """
                        SELECT id, summary, created_at
                        FROM tool_result_cache
                        WHERE created_at > ?
                        ORDER BY created_at DESC, id DESC
                        """,
                        (cutoff_created_at,),
                    ).fetchall()
                    legacy_hot_lines = [
                        line for row in reversed(hot_rows_desc)
                        if (line := _prompt_line(row))
                    ]
                    complete_hot_chars = (
                        len(_HOT_PROMPT_HEADER) + 2 + sum(len(line) for line in legacy_hot_lines)
                        if legacy_hot_lines
                        else 0
                    )
                    if not legacy_hot_lines or complete_hot_chars > TOOL_RESULT_HOT_MAX_CHARS:
                        if legacy_hot_lines:
                            snapshot_rows = conn.execute(
                                """
                                SELECT id, summary, created_at
                                FROM tool_result_cache
                                ORDER BY created_at ASC, id ASC
                                """
                            ).fetchall()
                            frozen_text, frozen_entries = _snapshot_text(snapshot_rows)
                            cutoff_created_at = (
                                max(float(row["created_at"]) for row in snapshot_rows)
                                if snapshot_rows
                                else now
                            )
                            snapshot_created = True
                            snapshot_reason = "hot_overflow"
                        else:
                            snapshot_reason = "legacy_hot_empty"
                        lifecycle_mode = "rolling"
                        current_chunk_index = len(normalized_chunk_ids)
                        sealed_chunk_ids = list(normalized_chunk_ids)
                        hot_items = []
                        recent_tool_batches = []
                        conn.execute(
                            """
                            UPDATE prompt_tool_generation
                            SET frozen_text = ?, cutoff_created_at = ?,
                                lifecycle_mode = 'rolling', current_chunk_index = ?,
                                sealed_chunk_ids_json = ?, hot_items_json = '[]',
                                recent_tool_batches_json = '[]', updated_at = ?
                            WHERE window_id = ? AND generation_id = ?
                            """,
                            (
                                frozen_text,
                                cutoff_created_at,
                                current_chunk_index,
                                json.dumps(sealed_chunk_ids, ensure_ascii=False),
                                now,
                                normalized_window_id,
                                normalized_generation_id,
                            ),
                        )
                    else:
                        hot_items = [
                            {"id": str(row["id"]), "text": line}
                            for row, line in zip(reversed(hot_rows_desc), legacy_hot_lines)
                        ]
                        recent_tool_batches = []

                if lifecycle_mode == "rolling":
                    (
                        current_chunk_index,
                        sealed_chunk_ids,
                        hot_items,
                        recent_tool_batches,
                        current_sealed_logs,
                    ) = _seal_missing_tool_chunks(
                        generation_id=normalized_generation_id,
                        chunk_ids=normalized_chunk_ids,
                        current_chunk_index=current_chunk_index,
                        sealed_chunk_ids=sealed_chunk_ids,
                        hot_items=hot_items,
                        recent_tool_batches=recent_tool_batches,
                        chunk_item_ids=normalized_chunk_item_ids,
                    )
                    if current_sealed_logs:
                        sealed_logs.extend(current_sealed_logs)
                        conn.execute(
                            """
                            UPDATE prompt_tool_generation
                            SET current_chunk_index = ?, sealed_chunk_ids_json = ?,
                                hot_items_json = ?, recent_tool_batches_json = ?,
                                updated_at = ?
                            WHERE window_id = ? AND generation_id = ? AND lifecycle_mode = 'rolling'
                            """,
                            (
                                current_chunk_index,
                                json.dumps(sealed_chunk_ids, ensure_ascii=False),
                                json.dumps(hot_items, ensure_ascii=False),
                                json.dumps(recent_tool_batches, ensure_ascii=False),
                                now,
                                normalized_window_id,
                                normalized_generation_id,
                            ),
                        )
            conn.execute("COMMIT")
    except Exception:
        logger.warning(
            "tool generation prompt read failed window_id=%s generation_id=%s",
            normalized_window_id,
            normalized_generation_id,
            exc_info=True,
        )
        return {
            "generation_id": normalized_generation_id,
            "lifecycle_mode": "error",
            "activation_pending": False,
            "frozen_text": "",
            "recent_batches": [],
            "hot_blocks": [],
            "cutoff_created_at": 0.0,
            "frozen_entries": 0,
            "hot_entries": 0,
            "hot_chars": 0,
            "sealed_chunk_ids": [],
        }

    if snapshot_created or snapshot_reason == "legacy_hot_empty":
        logger.info(
            "tool_generation_snapshot window_id=%s generation_id=%s reason=%s frozen_entries=%s frozen_chars=%s cutoff_created_at=%s lifecycle_mode=%s",
            normalized_window_id,
            normalized_generation_id,
            snapshot_reason,
            frozen_entries,
            len(frozen_text),
            cutoff_created_at,
            lifecycle_mode,
        )
    for sealed_generation_id, chunk_index, chunk_id, entries, chars in sealed_logs:
        logger.info(
            "tool_chunk_window_sealed window_id=%s generation_id=%s chunk_index=%s summary_chunk_id=%s entries=%s chars=%s",
            normalized_window_id,
            sealed_generation_id,
            chunk_index,
            chunk_id,
            entries,
            chars,
        )

    hot_blocks = [str(item.get("text") or "").strip() for item in hot_items]
    hot_blocks = [text for text in hot_blocks if text]
    if hot_blocks:
        hot_blocks[0] = _HOT_PROMPT_HEADER + "\n\n" + hot_blocks[0]
    return {
        "generation_id": normalized_generation_id,
        "lifecycle_mode": lifecycle_mode,
        "activation_pending": lifecycle_mode != "rolling",
        "frozen_text": frozen_text,
        "recent_batches": list(recent_tool_batches),
        "hot_blocks": hot_blocks,
        "cutoff_created_at": cutoff_created_at,
        "frozen_entries": frozen_entries,
        "hot_entries": len(hot_blocks),
        "hot_chars": sum(len(block) for block in hot_blocks),
        "sealed_chunk_ids": list(sealed_chunk_ids),
        "current_chunk_index": current_chunk_index,
    }


def sync_prompt_generation_after_summary(
    *,
    window_id: str,
    generation_id: int,
    generation_chunk_ids: list[str],
    previous_generation_chunk_ids: list[str] | None = None,
    generation_chunk_item_ids: dict[str, list[str]] | None = None,
) -> bool:
    result = prompt_generation_contents(
        window_id=window_id,
        generation_id=generation_id,
        generation_chunk_ids=generation_chunk_ids,
        previous_generation_chunk_ids=previous_generation_chunk_ids,
        generation_chunk_item_ids=generation_chunk_item_ids,
    )
    expected = set(_normalized_chunk_ids(generation_chunk_ids))
    sealed = set(_normalized_chunk_ids(result.get("sealed_chunk_ids")))
    if result.get("activation_pending") is True:
        return True
    return (
        result.get("lifecycle_mode") == "rolling"
        and int(result.get("generation_id") or 0) == int(generation_id or 0)
        and expected.issubset(sealed)
    )
