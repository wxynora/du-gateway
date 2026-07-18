from __future__ import annotations

import copy
import json
from typing import Any

from services.hidden_blocks import HiddenBlockParser
from storage import secret_drawer_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso


logger = get_logger(__name__)

MARKER_START = "<<<DU_SECRET_SAVE>>>"
MARKER_END = "<<<END_DU_SECRET_SAVE>>>"
_HIDDEN_BLOCK = HiddenBlockParser.for_markers("DU_SECRET_SAVE", MARKER_START, MARKER_END)


def compute_visible_streaming(acc: str) -> str:
    return _HIDDEN_BLOCK.compute_visible_streaming(acc)


def split_assistant_for_secret_drawer(text: str) -> tuple[str, str | None]:
    return _HIDDEN_BLOCK.split(text or "")


def split_all_assistant_for_secret_drawer(text: str) -> tuple[str, list[str]]:
    return _HIDDEN_BLOCK.split_all(text or "")


def _json_payload(raw: str) -> dict:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            typ = str(item.get("type") or "").strip().lower()
            if typ == "text":
                parts.append(str(item.get("text") or "").strip())
            elif typ == "image_url":
                parts.append("[图片]")
            elif typ == "input_audio":
                parts.append("[语音]")
        return "\n".join(x for x in parts if x).strip()
    return str(content or "").strip()


def _message_images(content: Any) -> list[dict]:
    refs: list[dict] = []
    if isinstance(content, list):
        for idx, item in enumerate(content):
            if not isinstance(item, dict):
                continue
            typ = str(item.get("type") or "").strip().lower()
            if typ not in {"image_url", "image"}:
                continue
            image_url = item.get("image_url") if isinstance(item.get("image_url"), dict) else {}
            url = str((image_url or {}).get("url") or item.get("url") or "").strip()
            if url:
                refs.append({"kind": "image", "url": url, "name": f"message-image-{idx}.jpg"})
    return refs


def _message_attachment_refs(message: dict) -> list[dict]:
    refs: list[dict] = []
    for item in (message or {}).get("attachments") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind and kind != "image":
            continue
        refs.append(
            {
                "kind": "image",
                "key": item.get("remoteKey") or item.get("key") or "",
                "url": item.get("remoteUrl") or item.get("url") or item.get("src") or "",
                "name": item.get("name") or item.get("filename") or "",
                "contentType": item.get("mime") or item.get("contentType") or "",
                "size": item.get("size") or 0,
            }
        )
    return refs


def _last_user_message(messages: list[dict]) -> dict:
    for msg in reversed(messages or []):
        if isinstance(msg, dict) and str(msg.get("role") or "").strip().lower() == "user":
            return msg
    return {}


def _source_from_context(context: dict) -> dict:
    ctx = context if isinstance(context, dict) else {}
    user_msg = ctx.get("user_message") if isinstance(ctx.get("user_message"), dict) else {}
    message_ids = []
    for key in ("id", "message_id", "messageId", "clientRequestId", "operationId"):
        val = str(user_msg.get(key) or "").strip()
        if val:
            message_ids.append(val)
    return {
        "channel": str(ctx.get("reply_channel") or ctx.get("channel") or "").strip(),
        "window_id": str(ctx.get("window_id") or "").strip(),
        "turn_id": str(ctx.get("turn_id") or ctx.get("client_request_id") or "").strip(),
        "message_ids": message_ids,
        "url": str(ctx.get("source_url") or "").strip(),
    }


def _safe_limit(value: Any, default: int = 20, *, min_value: int = 1, max_value: int = 500) -> int:
    try:
        n = int(float(str(value or default).strip()))
    except Exception:
        n = default
    return max(min_value, min(max_value, n))


def _optional_bool_arg(args: dict, key: str) -> bool | None:
    if not isinstance(args, dict) or key not in args:
        return None
    return _bool_value(args.get(key))


def _default_title(item_type: str, payload: dict) -> str:
    explicit = str(payload.get("title") or "").strip()
    if explicit:
        return explicit[:120]
    labels = {
        "message": "存下的一轮对话",
        "photo": "存下的一张图",
        "dream": "梦境记录",
        "note": "碎碎念",
        "surf": "冲浪记录",
        "misc": "秘密抽屉记录",
    }
    return labels.get(item_type, "秘密抽屉记录")


def _build_item_from_payload(payload: dict, context: dict) -> tuple[dict | None, str]:
    action = str(payload.get("action") or "").strip().lower()
    item_type = secret_drawer_store.VALID_ACTION_TYPES.get(action) or secret_drawer_store._normalize_type(payload.get("type"))
    if item_type not in secret_drawer_store.VALID_TYPES:
        item_type = "misc"

    messages = context.get("source_messages") if isinstance(context.get("source_messages"), list) else []
    user_msg = context.get("user_message") if isinstance(context.get("user_message"), dict) else _last_user_message(messages)
    assistant_text = str(context.get("assistant_text") or "").strip()
    user_text = _message_content_text(user_msg.get("content"))
    image_refs = _message_images(user_msg.get("content")) + _message_attachment_refs(user_msg)
    media_refs = []
    source = _source_from_context({**context, "user_message": user_msg})
    payload_source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    if payload_source:
        normalized_source = secret_drawer_store._normalize_source(payload_source)
        source = {**source, **{k: v for k, v in normalized_source.items() if v}}

    content = str(payload.get("content") or "").strip()
    if action == "save_message":
        media_refs = secret_drawer_store.ensure_media_refs(image_refs)
        parts = []
        if user_text:
            parts.append(f"小玥：{user_text}")
        if assistant_text:
            parts.append(f"渡：{assistant_text}")
        content = content or "\n\n".join(parts).strip()
    elif action == "save_photo":
        media_refs = secret_drawer_store.ensure_media_refs(image_refs)
        if not media_refs:
            return None, "当前消息里没有可保存的图片"
        content = content or str(payload.get("note") or user_text or "").strip()
    elif action == "save_dream":
        content = content or assistant_text or user_text
    elif action == "save_note":
        content = content or str(payload.get("note") or "").strip()
    elif action == "save_surf" or item_type == "surf":
        source["url"] = str(payload.get("source_url") or payload.get("url") or source.get("url") or "").strip()
        content = content or str(payload.get("summary") or payload.get("snippet") or "").strip()
    else:
        media_refs = secret_drawer_store.ensure_media_refs(
            secret_drawer_store._normalize_media_refs(payload.get("media_refs") or payload.get("mediaRefs"))
        )
    payload_media_refs = secret_drawer_store._normalize_media_refs(payload.get("media_refs") or payload.get("mediaRefs"))
    if payload_media_refs:
        media_refs = secret_drawer_store.ensure_media_refs([*media_refs, *payload_media_refs])

    if not content and not media_refs:
        return None, "没有可保存的内容"

    return {
        "type": item_type,
        "title": _default_title(item_type, payload),
        "content": content,
        "media_refs": media_refs,
        "why": str(payload.get("why") or "").strip(),
        "tags": payload.get("tags") or [],
        "pinned": bool(payload.get("pinned")),
        "sealed": bool(payload.get("sealed")),
        "source": source,
        "created_at": now_beijing_iso(),
    }, ""


def save_payload(payload: dict, context: dict | None = None) -> dict:
    item, err = _build_item_from_payload(payload if isinstance(payload, dict) else {}, context or {})
    if err:
        logger.warning("secret_drawer save skipped err=%s", err)
        return {"ok": False, "error": err}
    saved = secret_drawer_store.save_item(item or {})
    if not saved:
        logger.warning("secret_drawer save failed")
        return {"ok": False, "error": "写入失败"}
    logger.info("secret_drawer saved id=%s type=%s sealed=%s", saved.get("id"), saved.get("type"), saved.get("sealed"))
    return {"ok": True, "item": saved}


def save_hidden_block(
    raw_payload: str,
    *,
    window_id: str = "",
    source_messages: list[dict] | None = None,
    assistant_text: str = "",
    reply_channel: str = "",
) -> dict:
    payload = _json_payload(raw_payload)
    if not payload:
        return {"ok": False, "error": "隐藏保存块不是有效 JSON"}
    messages = copy.deepcopy(source_messages or [])
    context = {
        "window_id": window_id,
        "source_messages": messages,
        "user_message": _last_user_message(messages),
        "assistant_text": assistant_text,
        "reply_channel": reply_channel,
    }
    result = save_payload(payload, context)
    if not result.get("ok"):
        logger.warning("secret_drawer hidden save failed window_id=%s error=%s", window_id, result.get("error"))
    else:
        try:
            from services.tool_result_cache import record_tool_result

            saved = result.get("item") if isinstance(result.get("item"), dict) else {}
            record_tool_result(
                tool_call_id=f"secret-drawer-hidden:{saved.get('id') or ''}",
                name="secret_drawer",
                arguments={"action": str(payload.get("action") or "save"), "payload": payload},
                result=result,
                window_id=window_id,
                reply_channel=reply_channel,
            )
        except Exception:
            logger.warning("secret_drawer hidden save summary failed window_id=%s", window_id, exc_info=True)
    return result


def format_inject_block() -> str:
    st = secret_drawer_store.stats()
    config = secret_drawer_store.get_config()
    total = int(st.get("total") or 0)
    by_type = st.get("by_type") if isinstance(st.get("by_type"), dict) else {}
    lines = [
        "###秘密抽屉",
        "你有自己的秘密抽屉，可保存想留下的话、图片、梦境、冲浪内容或碎碎念。保存当前聊天用隐藏标记。",
        "保存时按内容选择分类：对话/聊天片段用 save_message，图片用 save_photo，梦或春梦用 save_dream，自己的想法/碎碎念用 save_note，网上看到的内容用 save_surf。不要把所有内容都存成 save_message。",
        "整理已有条目时，type 只使用 message、photo、dream、note、surf、misc；图片是 photo，不是 image；对话是 message，不是 dialog。",
    ]
    if total <= 0:
        lines.append("当前抽屉还是空的。")
    else:
        lines.append(f"当前抽屉：共 {total} 条。")
        lines.append(
            "分类："
            f"对话 {int(by_type.get('message') or 0)}、"
            f"图片 {int(by_type.get('photo') or 0)}、"
            f"梦境 {int(by_type.get('dream') or 0)}、"
            f"碎碎念 {int(by_type.get('note') or 0)}、"
            f"冲浪 {int(by_type.get('surf') or 0)}、"
            f"其他 {int(by_type.get('misc') or 0)}。"
        )
        lines.append(
            f"置顶 {int(st.get('pinned') or 0)} 条，暗格 {int(st.get('sealed') or 0)} 条，待整理 {int(st.get('needs整理') or 0)} 条。"
        )
    if not config.get("read_error") and not str(config.get("box_pin") or "").strip():
        lines.append("PIN 未设置，默认 0000；可用 secret_drawer 的 set_pin 设置 UI 解锁 PIN。")
    lines.append(
        "隐藏保存时，在 <<<DU_SECRET_SAVE>>> 与 <<<END_DU_SECRET_SAVE>>> 之间输出 JSON；"
        "action 必须按内容从 save_message、save_photo、save_dream、save_note、save_surf 中选择，"
        "其余可填 title、tags、why、sealed。"
    )
    lines.append(
        "整理/查看用工具 secret_drawer；action=stats/list/get/update/delete/restore/random/set_pin，参数放 payload。"
    )
    return "\n".join(lines).strip()


def get_secret_drawer_tools_for_inject() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "secret_drawer",
                "description": (
                    "查看/整理秘密抽屉。action=stats/list/get/update/delete/restore/random/set_pin；"
                    "参数放 payload；get/update/delete/restore 需 id。update 的 type 只能是 message/photo/dream/note/surf/misc，"
                    "图片用 photo（不是 image），对话用 message（不是 dialog）。保存当前聊天用 DU_SECRET_SAVE 隐藏标记，不用工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["stats", "list", "get", "update", "delete", "restore", "random", "set_pin"],
                            "description": "要做什么",
                        },
                        "payload": {
                            "type": "object",
                            "description": "具体参数；update 时按内容填写正确 type。",
                            "properties": {
                                "id": {"type": "string", "description": "get/update/delete/restore 的条目 id"},
                                "type": {
                                    "type": "string",
                                    "enum": ["message", "photo", "dream", "note", "surf", "misc"],
                                    "description": "条目分类：对话 message、图片 photo、梦境 dream、碎碎念 note、冲浪 surf、其他 misc",
                                },
                                "query": {"type": "string"},
                                "tag": {"type": "string"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "title": {"type": "string"},
                                "why": {"type": "string"},
                                "limit": {"type": "integer"},
                                "include_sealed": {"type": "boolean"},
                                "sealed_only": {"type": "boolean"},
                                "needs_organize": {"type": "boolean"},
                                "pinned": {"type": "boolean"},
                                "sealed": {"type": "boolean"},
                                "deleted": {"type": "boolean"},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def execute_secret_drawer_tool(name: str, arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
    action = str(args.get("action") or "").strip().lower()
    try:
        if name != "secret_drawer":
            return json.dumps({"ok": False, "error": "UNKNOWN_TOOL"}, ensure_ascii=False)
        if action == "stats":
            return json.dumps(
                {"ok": True, "stats": secret_drawer_store.stats(include_sealed_details=_bool_value(payload.get("include_sealed_details")))},
                ensure_ascii=False,
            )
        if action == "list":
            items = secret_drawer_store.list_items(
                include_deleted=_bool_value(payload.get("include_deleted")),
                include_sealed=_bool_value(payload.get("include_sealed")),
                sealed_only=_bool_value(payload.get("sealed_only")),
                type_filter=str(payload.get("type") or ""),
                tag=str(payload.get("tag") or ""),
                query=str(payload.get("query") or ""),
                needs_organize_only=_bool_value(payload.get("needs_organize")),
                pinned_only=_optional_bool_arg(payload, "pinned"),
                limit=_safe_limit(payload.get("limit"), 20),
            )
            summaries = [
                {
                    "id": it.get("id"),
                    "type": it.get("type"),
                    "title": it.get("title"),
                    "why": it.get("why"),
                    "tags": it.get("tags"),
                    "pinned": it.get("pinned"),
                    "sealed": it.get("sealed"),
                    "deleted": it.get("deleted"),
                    "has_media": bool(it.get("media_refs")),
                    "needs_organize": secret_drawer_store.needs_organize(it),
                    "created_at": it.get("created_at"),
                    "updated_at": it.get("updated_at"),
                }
                for it in items
            ]
            return json.dumps({"ok": True, "items": summaries, "count": len(summaries)}, ensure_ascii=False)
        if action == "get":
            item = secret_drawer_store.get_item(str(payload.get("id") or ""), include_deleted=_bool_value(payload.get("include_deleted")))
            return json.dumps({"ok": bool(item), "item": item, **({} if item else {"error": "未找到"})}, ensure_ascii=False)
        if action == "update":
            item_id = str(payload.get("id") or "").strip()
            patch_keys = {"title", "content", "why", "tags", "pinned", "sealed", "deleted", "type"}
            patch = {k: v for k, v in payload.items() if k in patch_keys}
            if "type" in patch:
                requested_type = str(patch.get("type") or "").strip().lower()
                if requested_type not in secret_drawer_store.VALID_TYPES:
                    return json.dumps(
                        {
                            "ok": False,
                            "error": "INVALID_TYPE",
                            "valid_types": sorted(secret_drawer_store.VALID_TYPES),
                        },
                        ensure_ascii=False,
                    )
            item = secret_drawer_store.update_item(item_id, patch)
            return json.dumps({"ok": bool(item), "item": item, **({} if item else {"error": "未找到或更新失败"})}, ensure_ascii=False)
        if action == "delete":
            item = secret_drawer_store.soft_delete_item(str(payload.get("id") or ""))
            return json.dumps({"ok": bool(item), "item": item, **({} if item else {"error": "未找到或删除失败"})}, ensure_ascii=False)
        if action == "restore":
            item = secret_drawer_store.restore_item(str(payload.get("id") or ""))
            return json.dumps({"ok": bool(item), "item": item, **({} if item else {"error": "未找到或恢复失败"})}, ensure_ascii=False)
        if action == "random":
            item = secret_drawer_store.random_item(
                include_sealed=_bool_value(payload.get("include_sealed")),
                sealed_only=_bool_value(payload.get("sealed_only")),
                type_filter=str(payload.get("type") or ""),
                tag=str(payload.get("tag") or ""),
                needs_organize_only=_bool_value(payload.get("needs_organize")),
            )
            return json.dumps({"ok": bool(item), "item": item, **({} if item else {"error": "没有可抽的条目"})}, ensure_ascii=False)
        if action == "set_pin":
            ok, config_or_error = secret_drawer_store.set_pin(str(payload.get("layer") or "box"), payload.get("pin"))
            return json.dumps(
                {
                    "ok": bool(ok),
                    **({} if ok else config_or_error),
                    **(
                        {
                            "configured": {
                                "box": bool((config_or_error or {}).get("box_pin")),
                                "sealed": bool((config_or_error or {}).get("sealed_pin")),
                            }
                        }
                        if ok
                        else {}
                    ),
                },
                ensure_ascii=False,
            )
    except Exception as e:
        logger.exception("secret_drawer tool failed name=%s", name)
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps({"ok": False, "error": "UNKNOWN_ACTION", "action": action}, ensure_ascii=False)


def _bool_value(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default
