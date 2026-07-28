from __future__ import annotations

from typing import Any

QQ_GROUP_CONTENT_MARKER = "[QQ_GROUP]"
QQ_GROUP_DELIVERY_MESSAGE_FIELD = "du_qq_group_delivery"


def split_qq_group_delivery_marker(text: str) -> tuple[bool, str]:
    raw = str(text or "")
    if not raw.startswith(QQ_GROUP_CONTENT_MARKER):
        return False, raw
    return True, raw[len(QQ_GROUP_CONTENT_MARKER) :].lstrip()


def apply_qq_group_delivery_marker(message: dict, *, group_id: str, enabled: bool) -> bool:
    """Consume the leading model marker and attach the backend-owned group target."""
    if not isinstance(message, dict):
        return False
    message.pop(QQ_GROUP_DELIVERY_MESSAGE_FIELD, None)
    if not enabled:
        return False
    target_group_id = str(group_id or "").strip()
    if not target_group_id:
        return False

    content: Any = message.get("content")
    if isinstance(content, str):
        marked, cleaned = split_qq_group_delivery_marker(content)
        if not marked:
            return False
        message["content"] = cleaned
    elif isinstance(content, list):
        updated = []
        marked = False
        for part in content:
            if marked or not isinstance(part, dict) or str(part.get("type") or "").strip() != "text":
                updated.append(part)
                continue
            text = str(part.get("text") or "")
            part_marked, cleaned = split_qq_group_delivery_marker(text)
            if not part_marked:
                updated.append(part)
                continue
            updated.append({**part, "text": cleaned})
            marked = True
        if not marked:
            return False
        message["content"] = updated
    else:
        return False

    message[QQ_GROUP_DELIVERY_MESSAGE_FIELD] = {"group_id": target_group_id}
    return True


def qq_group_delivery_target(message: dict) -> str:
    if not isinstance(message, dict):
        return ""
    meta = message.get(QQ_GROUP_DELIVERY_MESSAGE_FIELD)
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("group_id") or "").strip()
