import logging
import threading

from flask import jsonify, request

from config import TELEGRAM_PROACTIVE_TARGET_USER_ID
from storage import r2_store, whitelist_store


sumitalk_logger = logging.getLogger("sumitalk")


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


def _resolve_primary_chat_window_id() -> str:
    recent = whitelist_store.list_recent_windows(limit=200) or []
    for w in recent:
        wid = str((w or {}).get("id") or "").strip()
        if wid.startswith("tg_"):
            return wid
    uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if uid > 0:
        return f"tg_{uid}"
    if recent:
        return str((recent[0] or {}).get("id") or "").strip()
    return ""


def _choice_dialog_wakeup_event_text(item: dict) -> str:
    if not isinstance(item, dict) or str(item.get("type") or "").strip() != "show_choice_dialog":
        return ""
    if str(item.get("status") or "").strip().lower() != "done":
        return ""
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    if payload.get("notifyDu") is False:
        return ""
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    title = str(payload.get("title") or "弹窗").strip() or "弹窗"
    message = str(payload.get("message") or "").strip()
    label = str(result.get("label") or "").strip()
    choice_id = str(result.get("choice_id") or "").strip()
    if result.get("timeout"):
        outcome = "她没有选择，弹窗已超时关闭。"
    elif result.get("dismissed") or choice_id == "dismissed":
        outcome = "她关闭了弹窗，没有选择选项。"
    elif label:
        outcome = f"她选择了「{label}」。"
    else:
        return ""
    context = f"弹窗标题：{title}"
    if message:
        context += f"\n弹窗正文：{message}"
    return f"你刚刚发到她手机上的 SumiTalk 双选项弹窗收到了回应。\n{context}\n弹窗结果：{outcome}"


def _screen_check_wakeup_event(item: dict) -> dict:
    if not isinstance(item, dict) or str(item.get("type") or "").strip() != "request_screen_check":
        return {}
    if str(item.get("status") or "").strip().lower() != "done":
        return {}
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    title = str(payload.get("title") or "查岗申请").strip() or "查岗申请"
    message = str(payload.get("message") or "").strip()
    if not result.get("approved"):
        reason = str(result.get("reason") or result.get("choice_id") or "declined").strip()
        stage = str(result.get("stage") or "").strip()
        error = str(result.get("error") or "").strip()
        if stage == "capture_wait" or reason == "capture_timeout":
            outcome = "她点了 SumiTalk 的同意，但截图流程超时了，所以这次没有截图。"
        elif result.get("timeout") or reason == "timeout":
            outcome = "她没有同意，申请已超时。"
        elif result.get("dismissed") or reason == "dismissed":
            outcome = "她关闭了申请，没有同意截图。"
        elif stage == "system_capture_permission" or reason == "system_permission_denied":
            outcome = "她点了 SumiTalk 的同意，但 Android 系统截屏授权没有完成，所以这次没有截图。"
        elif stage == "accessibility_screenshot":
            outcome = "她点了同意，但 SumiTalk 辅助功能截图失败了，所以这次没有截图。"
            if error:
                outcome += f"\n错误：{error[:120]}"
        elif stage in {"screen_capture", "capture_upload"} or error:
            outcome = "她点了同意，但截图流程失败了，所以这次没有截图。"
            if error:
                outcome += f"\n错误：{error[:120]}"
        else:
            outcome = "她拒绝了这次截图申请。"
        context = f"查岗申请标题：{title}"
        if message:
            context += f"\n查岗申请正文：{message}"
        return {"text": f"你刚刚向她手机发起的查岗截图申请有结果了。\n{context}\n结果：{outcome}", "image_url": ""}
    image_url = str(result.get("image_url") or result.get("url") or "").strip()
    captured_at = str(result.get("captured_at") or result.get("capturedAt") or "").strip()
    if not image_url:
        return {"text": "她同意了查岗截图，但截图上传结果里没有可用图片链接。", "image_url": ""}
    text = "你刚刚向她手机发起的查岗截图申请有结果了：她同意了，这是她刚才的手机截图。"
    if captured_at:
        text += f"\n截图时间：{captured_at}"
    text += "\n请根据截图自然回应，不要说成监控或系统流程；如果看不清，就直接说看不清。"
    return {"text": text, "image_url": image_url}


def _wake_du_for_device_action_results(device_id: str, items: list[dict]) -> int:
    events = []
    for item in items or []:
        text = _choice_dialog_wakeup_event_text(item)
        if text:
            events.append({"text": text, "image_url": "", "kind": "choice_dialog"})
            continue
        screen_event = _screen_check_wakeup_event(item)
        if screen_event:
            screen_event["kind"] = "screen_check"
            events.append(screen_event)
    if not events:
        return 0
    window_id = _resolve_primary_chat_window_id()
    if not window_id:
        sumitalk_logger.warning("choice_dialog_wakeup_skip reason=no_window device_id=%s events=%s", device_id, len(events))
        return 0

    def _run() -> None:
        try:
            from services.conversation_followup import send_choice_dialog_wakeup
            from services.conversation_followup import send_screen_check_wakeup

            for event in events:
                if event.get("kind") == "screen_check":
                    result = send_screen_check_wakeup(
                        window_id=window_id,
                        target=device_id,
                        event_text=str(event.get("text") or ""),
                        image_url=str(event.get("image_url") or ""),
                    )
                else:
                    result = send_choice_dialog_wakeup(window_id=window_id, target=device_id, event_text=str(event.get("text") or ""))
                sumitalk_logger.info(
                    "choice_dialog_wakeup_done ok=%s device_id=%s window_id=%s channel=%s preferred=%s error=%s preview=%s",
                    bool(result.get("ok")),
                    device_id,
                    window_id,
                    str(result.get("channel") or ""),
                    str(result.get("preferred_channel") or ""),
                    str(result.get("error") or ""),
                    str(result.get("reply_preview") or "")[:80],
                )
        except Exception:
            sumitalk_logger.exception("choice_dialog_wakeup_failed device_id=%s window_id=%s", device_id, window_id)

    threading.Thread(target=_run, daemon=True).start()
    return len(events)


def register_routes(bp) -> None:
    @bp.route("/device-actions", methods=["GET"])
    def miniapp_device_actions():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识", "actions": []}), 400
        try:
            limit = int(request.args.get("limit") or 10)
        except Exception:
            limit = 10
        result = r2_store.poll_app_actions(device_id=device_id, limit=limit)
        actions = result.get("actions") if isinstance(result, dict) else None
        if isinstance(actions, list) and actions:
            sumitalk_logger.info(
                "device_actions_poll device_id=%s count=%s ids=%s types=%s",
                device_id,
                len(actions),
                [str((x or {}).get("id") or "") for x in actions if isinstance(x, dict)],
                [str((x or {}).get("type") or "") for x in actions if isinstance(x, dict)],
            )
        return jsonify(result)

    @bp.route("/device-actions/done", methods=["POST"])
    def miniapp_device_actions_done():
        device_id = _get_panel_device_id()
        if not device_id:
            return jsonify({"ok": False, "error": "缺少设备标识"}), 400
        body = request.get_json(silent=True) or {}
        results = body.get("results")
        if not isinstance(results, list):
            return jsonify({"ok": False, "error": "results 必须是数组"}), 400
        result = r2_store.report_app_actions(results, device_id=device_id)
        sumitalk_logger.info(
            "device_actions_done device_id=%s result_count=%s ok=%s processed=%s ids=%s statuses=%s",
            device_id,
            len(results),
            bool(result.get("ok")),
            result.get("processed"),
            [str((x or {}).get("id") or "") for x in results if isinstance(x, dict)],
            [str((x or {}).get("status") or "") for x in results if isinstance(x, dict)],
        )
        if result.get("ok"):
            queued = _wake_du_for_device_action_results(device_id, result.get("items") or [])
            if queued:
                result["proactive_wakeup_queued"] = queued
        return jsonify(result)
