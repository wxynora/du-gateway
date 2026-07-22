from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from services.hidden_blocks import HiddenBlockParser


MARKER_START = "<<<DU_LISTEN_INVITE>>>"
MARKER_END = "<<<END_DU_LISTEN_INVITE>>>"
_HIDDEN_BLOCK = HiddenBlockParser.for_markers(
    "DU_LISTEN_INVITE",
    MARKER_START,
    MARKER_END,
    short_markers=("du:listen",),
)
_CARD_RE = re.compile(r"<<<SUMITALK_CARD\s+(\{.*?\})>>>", re.DOTALL)
_VALID_ACTIONS = {"invite", "join", "refuse"}


def compute_visible_streaming(text: str) -> str:
    return _HIDDEN_BLOCK.compute_visible_streaming(str(text or ""))


def split_listen_invite_actions(text: str) -> tuple[str, list[str]]:
    visible, raw_actions = _HIDDEN_BLOCK.split_all(str(text or ""))
    actions: list[str] = []
    for raw in raw_actions:
        action = _normalize_action(raw)
        if action and action not in actions:
            actions.append(action)
    return visible, actions


def latest_user_listen_invite(messages: list[dict] | None) -> dict:
    for message in reversed(messages or []):
        if not isinstance(message, dict) or str(message.get("role") or "").strip().lower() != "user":
            continue
        text = _message_text(message)
        for match in reversed(list(_CARD_RE.finditer(text))):
            try:
                payload = json.loads(match.group(1))
            except Exception:
                continue
            if isinstance(payload, dict) and str(payload.get("type") or "").strip() == "listen_invite":
                return _normalize_invite_payload(payload)
        return {}
    return {}


def inject_listen_invite_protocol(body: dict, *, reply_channel: str = "") -> dict:
    if not isinstance(body, dict) or str(reply_channel or "").strip().lower() != "sumitalk":
        return body
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    invite = latest_user_listen_invite(messages)
    lines = [
        "【SumiTalk 一起听邀请控制标记】",
        "这里不用工具。控制标记只写在正常回复末尾，客户端会隐藏，不能在正文里解释或复述。",
        "你确实想主动邀请小玥一起听时，可以在回复末尾单独追加：[du:listen invite]。没有明确想邀请就不要追加。",
    ]
    if invite:
        lines.extend(
            [
                "小玥刚发送了一张一起听邀请卡片，意思是：小玥邀请你一起听音乐。",
                "你要按自己真实意愿二选一，并在自然回复末尾单独追加一个标记：参与用 [du:listen join]，拒绝用 [du:listen refuse]。",
                "本轮不能再发 invite，也不能省略 join/refuse。",
            ]
        )
    next_body = dict(body)
    next_body["messages"] = [
        {
            "role": "system",
            "content": "\n".join(lines),
            "__dynamic__": True,
            "__temporary_dynamic__": True,
        },
        *list(messages),
    ]
    return next_body


def build_listen_invite_event(action: str, *, messages: list[dict] | None = None) -> dict | None:
    normalized = _normalize_action(action)
    if normalized not in _VALID_ACTIONS:
        return None
    invite = latest_user_listen_invite(messages)
    if normalized in {"join", "refuse"} and not invite:
        return None
    if normalized == "invite":
        invite = _latest_music_entry()
    return {
        "part_id": "listen-invite-action",
        "action": normalized,
        "invite_id": str(invite.get("invite_id") or f"listen-{uuid4().hex}").strip(),
        "entry_id": str(invite.get("entry_id") or "").strip(),
        "title": str(invite.get("title") or "").strip(),
        "artist": str(invite.get("artist") or "").strip(),
        "subtitle": str(invite.get("subtitle") or _subtitle(invite)).strip(),
    }


def _latest_music_entry() -> dict:
    try:
        from storage.music_melody_store import list_music_melody_entries

        entries = list_music_melody_entries(limit=1) or []
    except Exception:
        entries = []
    item = entries[0] if entries and isinstance(entries[0], dict) else {}
    return _normalize_invite_payload(item)


def _normalize_action(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except Exception:
            obj = {}
        if isinstance(obj, dict):
            text = str(obj.get("action") or "").strip().lower()
    return re.split(r"[\s,，;；]+", text, maxsplit=1)[0] if text else ""


def _normalize_invite_payload(raw: dict) -> dict:
    return {
        "invite_id": str(raw.get("invite_id") or raw.get("inviteId") or "").strip(),
        "entry_id": str(raw.get("entry_id") or raw.get("entryId") or raw.get("remote_id") or raw.get("id") or "").strip(),
        "title": str(raw.get("track_title") or raw.get("title") or "").strip(),
        "artist": str(raw.get("artist") or "").strip(),
        "subtitle": str(raw.get("subtitle") or "").strip(),
    }


def _subtitle(invite: dict) -> str:
    title = str(invite.get("title") or "").strip()
    artist = str(invite.get("artist") or "").strip()
    return " · ".join(x for x in (title, artist) if x) or "点开回应渡的邀请"


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item.get("text") or "")
    return "\n".join(parts)
