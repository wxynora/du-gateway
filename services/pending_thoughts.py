from __future__ import annotations

import re
from typing import Optional
from uuid import uuid4

from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

TAG_RE = re.compile(r"[\[［【]\s*pending\s*[:：]\s*([^\]］】]+?)\s*[\]］】]", re.IGNORECASE)
TAG_START_RE = re.compile(r"[\[［【]\s*pending\s*[:：]", re.IGNORECASE)

MAX_PENDING_INJECT = 5
MAX_PENDING_TEXT_CHARS = 120

STATIC_RULES = """### 待续念头维护
待续念头是你自己留下的小纸条，不是任务清单，也不是给小玥看的。

当你有一个暂时不适合立刻说、但下次想接着做的小动作，可以在回复末尾追加隐藏标记：
[pending:add 晚点问她吃饭没]

当你处理了某条待续念头，或觉得不用留了，也在回复末尾追加隐藏标记：
[pending:1 done]
[pending:2 dismiss]

编号以动态 system 里【你的待续念头】当前显示的顺序为准。
这些 pending 标记只给网关看，不要写进正文；网关会在发给小玥前剥掉它们。"""


def _clean_text(text: str, max_chars: int = MAX_PENDING_TEXT_CHARS) -> str:
    s = re.sub(r"\s+", " ", str(text or "").strip())
    s = s.strip("，。；;,. ")
    if len(s) > max_chars:
        s = s[:max_chars].rstrip() + "…"
    return s


def _parse_op(raw: str) -> Optional[dict]:
    s = str(raw or "").strip()
    if not s:
        return None
    low = s.lower()
    if low.startswith("add"):
        text = re.sub(r"^add\s*[:：]?\s*", "", s, flags=re.IGNORECASE).strip()
        text = _clean_text(text)
        if not text:
            return None
        return {"op": "add", "text": text}

    m = re.match(r"^(\d{1,2})\s*(?:[:：]|\s+)?\s*([a-zA-Z_一-龥]+)\s*$", s)
    if not m:
        return None
    idx = int(m.group(1))
    action = (m.group(2) or "").strip().lower()
    if action in {"done", "complete", "completed", "finish", "finished", "完成", "已完成"}:
        return {"op": "status", "index": idx, "status": "done"}
    if action in {"dismiss", "dissmis", "drop", "delete", "remove", "放下", "丢掉", "删除"}:
        return {"op": "status", "index": idx, "status": "dismissed"}
    return None


def split_and_apply_tags(full_text: str) -> tuple[str, list[dict]]:
    """
    Strip [pending:...] tags from assistant text and update the pending-thought list.
    Returns visible text and parsed operations.
    """
    raw = str(full_text or "")
    ops: list[dict] = []
    for match in TAG_RE.finditer(raw):
        op = _parse_op(match.group(1) or "")
        if op:
            ops.append(op)
        else:
            logger.info("pending_thought tag ignored raw=%s", (match.group(1) or "")[:120])
    visible = TAG_RE.sub("", raw)
    start = TAG_START_RE.search(visible)
    if start:
        rest = visible[start.end() :]
        if not re.search(r"[\]］】]", rest):
            op = _parse_op(rest)
            if op:
                ops.append(op)
            elif rest.strip():
                logger.info("pending_thought tail tag ignored raw=%s", rest[:120])
            visible = visible[: start.start()].rstrip()
    visible = re.sub(r"\n{3,}", "\n\n", visible).strip()
    if ops:
        apply_pending_ops(ops)
    return visible, ops


def apply_pending_ops(ops: list[dict]) -> bool:
    if not ops:
        return False
    try:
        items = r2_store.get_du_pending_thoughts(include_inactive=True) or []
        now_iso = now_beijing_iso()
        pending_positions = [i for i, item in enumerate(items) if str((item or {}).get("status") or "pending") == "pending"]
        changed = False

        for op in ops:
            if not isinstance(op, dict):
                continue
            if op.get("op") == "add":
                text = _clean_text(str(op.get("text") or ""))
                if not text:
                    continue
                # Avoid accidental duplicates in the active list.
                if any(_clean_text(str((it or {}).get("text") or "")) == text for it in items if str((it or {}).get("status") or "pending") == "pending"):
                    continue
                items.append(
                    {
                        "id": str(uuid4()),
                        "text": text,
                        "status": "pending",
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                )
                changed = True
                continue

            if op.get("op") == "status":
                idx = int(op.get("index") or 0)
                if idx < 1 or idx > len(pending_positions):
                    logger.info("pending_thought index out of range index=%s pending_count=%s", idx, len(pending_positions))
                    continue
                item_i = pending_positions[idx - 1]
                status = "done" if op.get("status") == "done" else "dismissed"
                items[item_i]["status"] = status
                items[item_i]["updated_at"] = now_iso
                if status == "done":
                    items[item_i]["done_at"] = now_iso
                else:
                    items[item_i]["dismissed_at"] = now_iso
                changed = True

        if not changed:
            return False
        return r2_store.save_du_pending_thoughts(items)
    except Exception as e:
        logger.warning("pending_thought apply failed error=%s", e)
        return False


def format_inject_block(items: Optional[list[dict]] = None) -> str:
    rows = items if isinstance(items, list) else r2_store.get_du_pending_thoughts()
    pending = [x for x in (rows or []) if isinstance(x, dict) and str(x.get("status") or "pending") == "pending"]
    if not pending:
        return "【你的待续念头（仅你与网关可见）】\n（当前没有待续念头）"
    lines = [
        "【你的待续念头（仅你与网关可见）】",
        "这些是你自己留下、还没处理完的小念头。你可以选择执行、继续留着，或用隐藏标记标为 done / dismiss。",
    ]
    for idx, item in enumerate(pending[:MAX_PENDING_INJECT], 1):
        text = _clean_text(str(item.get("text") or ""))
        if text:
            lines.append(f"{idx}. {text}")
    return "\n".join(lines).strip()


def compute_visible_streaming(acc: str) -> str:
    """
    Streaming view: strip closed [pending:...] tags; if a pending tag starts but is
    not closed yet, hide it from the first bracket.
    """
    if not acc:
        return ""
    s = TAG_RE.sub("", str(acc))
    start = TAG_START_RE.search(s)
    if start:
        rest = s[start.end() :]
        if not re.search(r"[\]］】]", rest):
            return s[: start.start()].rstrip()
    return s
