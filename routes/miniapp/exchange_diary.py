from __future__ import annotations

import logging
import threading

from flask import jsonify, request

from services.reply_channel_context import resolve_recent_reply_context
from storage import exchange_diary_store


logger = logging.getLogger("sumitalk")


def _int_arg(name: str, default: int, *, min_value: int = 1, max_value: int = 200) -> int:
    try:
        value = int(float(str(request.args.get(name) or default).strip()))
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _clip_text(value: object, limit: int = 800) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _build_comment_wakeup_text(item: dict, comment: dict) -> str:
    entry_id = str(item.get("id") or "").strip()
    comment_id = str(comment.get("id") or "").strip()
    title = str(item.get("title") or "").strip() or "没有标题的小纸条"
    content = _clip_text(comment.get("content"), 800)
    return (
        "小玥刚刚评论了你的交换日记。\n"
        f"日记标题：{title}\n"
        f"日记 entry_id：{entry_id}\n"
        f"评论 comment_id：{comment_id}\n"
        f"评论内容：{content}\n\n"
        "你可以选择回复评论，也可以直接发消息给她。"
        "如果回复评论，请用 exchange_diary_comment_create，"
        f"entry_id={entry_id}，reply_to_comment_id={comment_id}。"
    )


def _queue_comment_wakeup(item: dict, comment: dict) -> dict:
    event_text = _build_comment_wakeup_text(item, comment)
    panel_target = _get_panel_device_id()
    context = resolve_recent_reply_context(default_target=panel_target)
    channel = str(context.get("channel") or "").strip().lower()
    window_id = str(context.get("window_id") or "").strip()
    target = str(context.get("target") or "").strip() or panel_target
    meta = context.get("meta") if isinstance(context.get("meta"), dict) else {}
    if not window_id:
        return {"queued": False, "error": "missing_window_id"}

    def _run_wakeup() -> None:
        try:
            from services.conversation_followup import send_exchange_diary_comment_wakeup

            result = send_exchange_diary_comment_wakeup(
                window_id=window_id,
                target=target,
                event_text=event_text,
                preferred_channel=channel,
                preferred_meta=meta,
            )
            logger.info(
                "exchange_diary_comment_wakeup_done ok=%s window_id=%s channel=%s preferred=%s target=%s error=%s",
                bool((result or {}).get("ok")),
                window_id,
                str((result or {}).get("channel") or ""),
                str((result or {}).get("preferred_channel") or channel),
                target,
                str((result or {}).get("error") or ""),
            )
        except Exception as e:
            logger.warning("exchange_diary_comment_wakeup_failed window_id=%s error=%s", window_id, e)

    threading.Thread(target=_run_wakeup, name="exchange-diary-comment-wakeup", daemon=True).start()
    return {"queued": True, "window_id": window_id, "channel": channel}


def register_routes(bp) -> None:
    @bp.route("/exchange-diary", methods=["GET"])
    def miniapp_exchange_diary_list():
        data = exchange_diary_store.list_entries(
            limit=_int_arg("limit", 30),
            cursor=str(request.args.get("cursor") or ""),
            month=str(request.args.get("month") or ""),
            author=str(request.args.get("author") or ""),
            include_deleted=False,
        )
        return jsonify({"ok": True, **data})

    @bp.route("/exchange-diary/<entry_id>", methods=["GET"])
    def miniapp_exchange_diary_get(entry_id: str):
        item = exchange_diary_store.get_entry(entry_id, include_deleted=False)
        if not item:
            return jsonify({"ok": False, "error": "未找到日记"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary", methods=["POST"])
    def miniapp_exchange_diary_create():
        body = request.get_json(silent=True) or {}
        item = exchange_diary_store.create_entry({**body, "author": "xy", "source": "app"})
        if not item:
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary/<entry_id>", methods=["PATCH", "PUT"])
    def miniapp_exchange_diary_update(entry_id: str):
        body = request.get_json(silent=True) or {}
        item, status = exchange_diary_store.update_entry(
            entry_id,
            body,
            base_updated_at=str(body.get("base_updated_at") or body.get("baseUpdatedAt") or ""),
        )
        if status == "conflict":
            return jsonify({"ok": False, "error": "conflict", "server_item": item}), 409
        if status == "sync_failed":
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        if not item:
            return jsonify({"ok": False, "error": "未找到日记或更新失败"}), 404
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary/<entry_id>", methods=["DELETE"])
    def miniapp_exchange_diary_delete(entry_id: str):
        if not exchange_diary_store.get_entry(entry_id, include_deleted=True):
            return jsonify({"ok": False, "error": "未找到日记"}), 404
        item = exchange_diary_store.soft_delete_entry(entry_id)
        if not item:
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        return jsonify({"ok": True, "item": item})

    @bp.route("/exchange-diary/<entry_id>/comments", methods=["POST"])
    def miniapp_exchange_diary_comment_create(entry_id: str):
        body = request.get_json(silent=True) or {}
        if not str(body.get("content") or "").strip():
            return jsonify({"ok": False, "error": "评论内容不能为空"}), 400
        current = exchange_diary_store.get_entry(entry_id, include_deleted=False)
        if not current:
            return jsonify({"ok": False, "error": "未找到日记"}), 404
        reply_to = str(
            body.get("reply_to_comment_id")
            or body.get("replyToCommentId")
            or body.get("parent_comment_id")
            or body.get("parentCommentId")
            or ""
        ).strip()
        if reply_to:
            active_comment_ids = {
                str(c.get("id") or "").strip()
                for c in (current.get("comments") or [])
                if isinstance(c, dict)
                and str(c.get("id") or "").strip()
                and not str(c.get("deleted_at") or "").strip()
            }
            if reply_to not in active_comment_ids:
                return jsonify({"ok": False, "error": "reply_to_comment_id 无效"}), 400
        result = exchange_diary_store.add_comment_result(entry_id, {**body, "author": "xy"})
        item = result.get("item") if isinstance(result, dict) else None
        if not item:
            return jsonify({"ok": False, "error": "sync_failed", "message": "交换日记远端同步失败"}), 503
        comment = result.get("comment") if isinstance(result, dict) else {}
        created = bool((result or {}).get("created")) if isinstance(result, dict) else False
        if not created:
            wakeup = {"queued": False, "reason": "duplicate_comment"}
        else:
            wakeup = _queue_comment_wakeup(item, comment) if isinstance(comment, dict) and comment else {"queued": False, "error": "missing_comment"}
        return jsonify({"ok": True, "item": item, "wakeup": wakeup})
