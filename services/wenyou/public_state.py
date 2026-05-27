import ast
import re
from typing import Any, Optional

from utils.time_aware import now_beijing_iso

from services.wenyou.common import _compact_text, _slug_id
from services.wenyou.runtime_state import _normalize_text_list


def _panel_object_id(value: Any, prefix: str, index: int = 0) -> str:
    raw = _compact_text(value, 80)
    if not raw:
        return f"{prefix}_{index + 1}"
    slug = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "_", raw).strip("_")
    return (slug or f"{prefix}_{index + 1}")[:80]


def _normalize_public_task_item(item: Any, index: int, phase: str = "instance_running") -> Optional[dict]:
    status = "completed" if phase in {"settlement", "archived"} else "active"
    if isinstance(item, dict):
        title = _compact_text(item.get("title") or item.get("current") or item.get("goal") or item.get("public_text"), 160)
        if not title:
            return None
        progress = item.get("progress") if isinstance(item.get("progress"), dict) else {}
        return {
            "id": _panel_object_id(item.get("id") or title, "task", index),
            "title": title,
            "type": _compact_text(item.get("type") or "main", 40),
            "status": _compact_text(item.get("status") or status, 40),
            "progress": progress,
            "required_clues": _normalize_text_list(item.get("required_clues"), 80, 12),
            "related_clues": _normalize_text_list(item.get("related_clues"), 80, 12),
            "fail_forward": _compact_text(item.get("fail_forward"), 220),
            "reward_tags": _normalize_text_list(item.get("reward_tags"), 60, 12),
        }
    title = _compact_text(item, 160)
    if not title:
        return None
    return {
        "id": _panel_object_id(title, "task", index),
        "title": title,
        "type": "main" if index == 0 else "side",
        "status": status,
        "progress": {},
        "required_clues": [],
        "related_clues": [],
        "fail_forward": "",
        "reward_tags": [],
    }


def _normalize_public_clue_item(item: Any, index: int) -> Optional[dict]:
    if isinstance(item, str):
        raw = item.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                parsed = None
            if isinstance(parsed, dict):
                item = parsed
    if isinstance(item, dict):
        title = _compact_text(item.get("title") or item.get("name") or item.get("public_text") or item.get("text"), 120)
        text = _compact_text(item.get("public_text") or item.get("text") or item.get("reason") or title, 220)
        if not title and not text:
            return None
        return {
            "id": _panel_object_id(item.get("id") or title or text, "clue", index),
            "title": title or text,
            "status": _compact_text(item.get("status") or ("verified" if item.get("verified") else "discovered"), 40),
            "verified": bool(item.get("verified")),
            "source": _compact_text(item.get("source"), 80),
            "related_tasks": _normalize_text_list(item.get("related_tasks"), 80, 12),
            "leads_to": _normalize_text_list(item.get("leads_to"), 80, 12),
            "tags": _normalize_text_list(item.get("tags"), 40, 12),
            "public_text": text,
        }
    text = _compact_text(item, 220)
    if not text:
        return None
    return {
        "id": _panel_object_id(text, "clue", index),
        "title": text[:40],
        "status": "discovered",
        "verified": False,
        "source": "",
        "related_tasks": [],
        "leads_to": [],
        "tags": [],
        "public_text": text,
    }


def _normalize_public_marker_item(item: Any, index: int, prefix: str) -> Optional[dict]:
    if isinstance(item, dict):
        title = _compact_text(item.get("name") or item.get("title") or item.get("id"), 120)
        text = _compact_text(item.get("public_text") or item.get("desc") or item.get("blurb") or item.get("reason") or item.get("status"), 240)
        if not title and not text:
            return None
        out = {
            "id": _panel_object_id(item.get("id") or title or text, prefix, index),
            "name": title or text[:40],
            "status": _compact_text(item.get("status") or item.get("public_status"), 80),
            "public_text": text,
        }
        for key in (
            "danger",
            "last_location",
            "attitude",
            "weakness",
            "type",
            "tier",
            "rank",
            "stability",
            "stability_max",
            "seal_progress",
            "seal_target",
            "weaknesses",
            "counterplay",
        ):
            if item.get(key) is not None and item.get(key) != "":
                out[key] = item.get(key) if isinstance(item.get(key), (int, float, list)) else _compact_text(item.get(key), 120)
        return out
    text = _compact_text(item, 240)
    if not text:
        return None
    return {"id": _panel_object_id(text, prefix, index), "name": text[:40], "status": "", "public_text": text}


def _merge_panel_list(existing: Any, additions: list[dict], prefix: str, limit: int = 40) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for idx, item in enumerate(existing if isinstance(existing, list) else []):
        norm = (
            _normalize_public_task_item(item, idx)
            if prefix == "task"
            else _normalize_public_clue_item(item, idx)
            if prefix == "clue"
            else _normalize_public_marker_item(item, idx, prefix)
        )
        if norm:
            key = str(norm.get("id") or norm.get("title") or norm.get("name"))
            seen.add(key)
            out.append(norm)
    for item in additions:
        key = str(item.get("id") or item.get("title") or item.get("name"))
        if key in seen:
            for idx, cur in enumerate(out):
                if str(cur.get("id") or cur.get("title") or cur.get("name")) == key:
                    out[idx] = {**cur, **item}
                    break
            continue
        seen.add(key)
        out.append(item)
    return out[-limit:]


def _rules_mapping(raw: Any, prefix: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if isinstance(raw, dict):
        items = raw.values()
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        key = _slug_id(item.get("id") or item.get("name") or item.get("title") or f"{prefix}_{idx + 1}", f"{prefix}_{idx + 1}")
        cur = dict(item)
        cur["id"] = key
        out[key] = cur
    return out


def _infer_progress_status(text: Any, fallback: str = "active") -> str:
    body = _compact_text(text, 260)
    if re.search(r"(失败|错过|失效|死亡|团灭|崩坏)", body):
        return "failed"
    if re.search(r"(完成|达成|通关|验证成功|已验证|解决|封印|撤离成功|结算)", body):
        return "completed"
    if re.search(r"(隐藏|暗线)", body):
        return "hidden_completed" if re.search(r"(完成|达成|真结局)", body) else fallback
    return fallback


def _task_progress_entry(item: Any, index: int, phase: str, fallback_type: str = "main") -> Optional[dict]:
    task = _normalize_public_task_item(item, index, phase)
    if not task:
        return None
    text = " ".join(
        str(x or "")
        for x in (
            task.get("title"),
            task.get("status"),
            (task.get("progress") or {}).get("text") if isinstance(task.get("progress"), dict) else task.get("progress"),
        )
    )
    task["status"] = _infer_progress_status(text, str(task.get("status") or "active"))
    task["type"] = _compact_text(task.get("type") or fallback_type, 40)
    task["updated_at"] = now_beijing_iso()
    return task


def _clue_state_entry(item: Any, index: int, verified: bool = False, visibility: str = "public") -> Optional[dict]:
    clue = _normalize_public_clue_item(item, index)
    if not clue:
        return None
    clue["status"] = "verified" if verified or clue.get("verified") else _compact_text(clue.get("status") or "discovered", 40)
    clue["verified"] = bool(verified or clue.get("verified") or clue.get("status") == "verified")
    clue["visibility"] = "hidden" if visibility == "hidden" else "public"
    clue["updated_at"] = now_beijing_iso()
    return clue


def _marker_state_entry(item: Any, index: int, prefix: str, visibility: str = "hidden") -> Optional[dict]:
    marker = _normalize_public_marker_item(item, index, prefix)
    if not marker:
        return None
    marker["visibility"] = "public" if visibility == "public" else "hidden"
    marker["updated_at"] = now_beijing_iso()
    if isinstance(item, dict):
        for key in (
            "location",
            "last_location",
            "attitude",
            "stance",
            "intent",
            "trigger",
            "trouble_chance",
            "alive",
            "danger_level",
            "locked",
            "resources",
        ):
            if item.get(key) is not None:
                marker[key] = item.get(key) if isinstance(item.get(key), (int, float, bool, list, dict)) else _compact_text(item.get(key), 180)
    return marker


def _public_rule_update_stub(entry: dict) -> dict:
    return {
        "id": entry.get("id"),
        "name": entry.get("name") or entry.get("title"),
        "status": entry.get("status"),
        "visibility": entry.get("visibility") or "hidden",
    }


def _public_threat_label(session: dict) -> str:
    clocks = session.get("clocks") if isinstance(session.get("clocks"), list) else []
    ratios: list[float] = []
    for item in clocks:
        if not isinstance(item, dict):
            continue
        max_value = max(1, int(item.get("max") or 1))
        ratios.append(max(0.0, min(1.0, float(item.get("value") or 0) / max_value)))
    if not ratios:
        return "平稳"
    ratio = max(ratios)
    if ratio >= 1:
        return "接近清算"
    if ratio >= 0.67:
        return "高危"
    if ratio >= 0.34:
        return "升高"
    return "平稳"


def _public_clock_status(clock: Any) -> str:
    if not isinstance(clock, dict):
        return "未知"
    max_value = max(1, int(clock.get("max") or 1))
    ratio = max(0.0, min(1.0, float(clock.get("value") or 0) / max_value))
    if ratio >= 1:
        return "已满"
    if ratio >= 0.67:
        return "高危"
    if ratio >= 0.34:
        return "升高"
    if ratio > 0:
        return "轻微"
    return "平稳"
