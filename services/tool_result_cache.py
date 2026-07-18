"""Compact, local-only history of completed gateway tool calls."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import (
    TOOL_RESULT_CACHE_MAX_CHARS,
    TOOL_RESULT_CACHE_TRIM_TO_CHARS,
    TOOL_RESULT_CACHE_TTL_SECONDS,
)
from storage import runtime_sqlite
from utils.log import get_logger

logger = get_logger(__name__)

TOOL_RESULT_CACHE_SYSTEM_MARKER = "__tool_result_cache__"
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


def _text(value: Any, max_chars: int = 600) -> str:
    raw = str(value or "").replace("\r", " ").replace("\n", " ")
    raw = _SPACE_RE.sub(" ", raw).strip()
    raw = _SECRET_RE.sub(lambda m: f"{m.group(1)}***", raw)
    raw = _BEARER_RE.sub("Bearer ***", raw)
    if len(raw) > max_chars:
        raw = raw[:max_chars].rstrip(" ，,。；;:") + "…"
    return raw


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
    elif tool_name in {"forum_read_feed", "forum_open_thread", "cli", "get_guide"} or tool_name.startswith("forum_"):
        detail = _forum_detail(tool_name, args, data)
    elif tool_name == "web_search":
        detail = _web_search_detail(args, data)
    elif tool_name == "search_memory":
        detail = _memory_search_detail(args, data)
    elif data.get("game_tool_loop") is True or (data.get("game_id") and data.get("skip_dynamic_memory_write")):
        detail = _game_detail(tool_name, args, data)
    else:
        detail = _generic_detail(tool_name, args, result, data)
    detail = _text(detail, 800).strip()
    return f"使用 {tool_name} 结果：{detail or '未返回可读结果'}"


def _entry_id(tool_call_id: str, tool_name: str, window_id: str) -> str:
    raw = str(tool_call_id or "").strip()
    digest = hashlib.sha256(f"{window_id}\n{tool_name}\n{raw}".encode("utf-8")).hexdigest()
    return f"tool_{digest}"


def _prompt_line_chars(summary: str) -> int:
    return len(f"【00:00 {summary}】")


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
        tool_call_id = str(entry.get("tool_call_id") or "").strip()
        if not tool_call_id:
            fallback_raw = json.dumps(
                [name, entry.get("arguments"), entry.get("result")],
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            tool_call_id = f"missing-id:{hashlib.sha256(fallback_raw.encode('utf-8')).hexdigest()}"
        prepared.append(
            (
                _entry_id(tool_call_id, name, str(window_id or "")),
                name,
                summary,
            )
        )
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
    out: list[str] = []
    for row in rows:
        try:
            label = datetime.fromtimestamp(float(row["created_at"]), tz=_BEIJING).strftime("%H:%M")
        except Exception:
            label = "--:--"
        summary = _text(row["summary"], 900)
        if summary:
            out.append(f"【{label} {summary}】")
    return out


def prompt_system_contents() -> list[str]:
    return [_PROMPT_HEADER, *list_prompt_lines()]
