import logging
import threading

from flask import jsonify, request

from services.reply_channel_context import resolve_recent_reply_context
from storage import r2_store


sumitalk_logger = logging.getLogger("sumitalk")


def _get_panel_device_id() -> str:
    payload = request.environ.get("miniapp_panel_payload") or {}
    return str(payload.get("device_id") or "").strip()


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
    payload_window_id = str(payload.get("windowId") or payload.get("window_id") or "").strip()
    result_window_id = str(result.get("windowId") or result.get("window_id") or "").strip()
    if payload_window_id and result_window_id and payload_window_id != result_window_id:
        sumitalk_logger.warning(
            "recall_message_result_window_mismatch action_id=%s payload_window=%s result_window=%s",
            str(item.get("id") or ""),
            payload_window_id,
            result_window_id,
        )
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
    text += "\n请根据截图自然回应，如果看不清，就直接说看不清。"
    return {"text": text, "image_url": image_url}


def _recall_message_wakeup_event_text(item: dict) -> str:
    if not isinstance(item, dict) or str(item.get("type") or "").strip() != "recall_message":
        return ""
    if str(item.get("status") or "").strip().lower() != "done":
        return ""
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    raw_messages = result.get("recalledMessages")
    if not isinstance(raw_messages, list):
        raw_messages = result.get("recalled_messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        return ""
    payload_window_id = str(payload.get("windowId") or payload.get("window_id") or "").strip()
    result_window_id = str(result.get("windowId") or result.get("window_id") or "").strip()
    if payload_window_id and result_window_id and payload_window_id != result_window_id:
        sumitalk_logger.warning(
            "recall_message_result_window_mismatch action_id=%s payload_window=%s result_window=%s",
            str(item.get("id") or ""),
            payload_window_id,
            result_window_id,
        )
    lines = ["你刚刚在 SumiTalk App 里撤回了她的消息。"]
    for raw in raw_messages[:4]:
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or raw.get("text") or "").strip()
        if not content:
            continue
        if not content.startswith("【已撤回】"):
            content = f"【已撤回】{content}"
        if len(content) > 900:
            content = content[:900].rstrip() + "..."
        lines.append(f"你已撤回她的这条消息：\n{content}")
    choice_label = str(result.get("choiceLabel") or result.get("label") or "").strip()
    choice_id = str(result.get("choiceId") or result.get("choice_id") or "").strip()
    auto_selected = bool(result.get("autoSelected") or result.get("auto_selected"))
    if choice_label:
        if auto_selected:
            lines.append(f"最后的弹窗倒计时结束，已自动替她选择「{choice_label}」。")
        else:
            lines.append(f"她在最后的弹窗里选择了「{choice_label}」。")
    elif choice_id:
        if auto_selected:
            lines.append(f"最后的弹窗倒计时结束，已自动选择 {choice_id}。")
        else:
            lines.append(f"她在最后的弹窗里选择了 {choice_id}。")
    window_id = payload_window_id or result_window_id
    if window_id:
        lines.append(f"窗口：{window_id}")
    lines.append("请接着这个结果自然回应，记住这不是她撤回自己消息，是你撤回了她的这条消息。")
    return "\n".join([line for line in lines if line])


def _wake_du_for_device_action_results(device_id: str, items: list[dict]) -> int:
    events = []
    for item in items or []:
        recall_text = _recall_message_wakeup_event_text(item)
        if recall_text:
            try:
                from services.recall_message_markers import record_recall_message_result

                record_recall_message_result(item)
            except Exception:
                sumitalk_logger.debug("recall_message_marker_record_failed", exc_info=True)
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            result = item.get("result") if isinstance(item.get("result"), dict) else {}
            payload_window_id = str(payload.get("windowId") or payload.get("window_id") or "").strip()
            events.append({
                "text": recall_text,
                "image_url": "",
                "kind": "recall_message",
                "window_id": payload_window_id or str(result.get("windowId") or result.get("window_id") or "").strip(),
            })
            continue
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
    context = resolve_recent_reply_context(default_target=device_id)
    forced_window_id = next((str(event.get("window_id") or "").strip() for event in events if str(event.get("window_id") or "").strip()), "")
    window_id = forced_window_id or str(context.get("window_id") or "").strip()
    target = str(context.get("target") or "").strip() or device_id
    channel = str(context.get("channel") or "").strip().lower()
    meta = context.get("meta") if isinstance(context.get("meta"), dict) else {}
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
                        target=target,
                        event_text=str(event.get("text") or ""),
                        image_url=str(event.get("image_url") or ""),
                        preferred_channel=channel,
                        preferred_meta=meta,
                    )
                else:
                    result = send_choice_dialog_wakeup(
                        window_id=window_id,
                        target=target,
                        event_text=str(event.get("text") or ""),
                        preferred_channel=channel,
                        preferred_meta=meta,
                    )
                sumitalk_logger.info(
                    "choice_dialog_wakeup_done ok=%s device_id=%s window_id=%s target=%s channel=%s preferred=%s error=%s preview=%s",
                    bool(result.get("ok")),
                    device_id,
                    window_id,
                    target,
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
        surface = str(request.args.get("surface") or "native").strip().lower()
        window_id = str(request.args.get("window_id") or request.args.get("windowId") or "").strip()
        result = r2_store.poll_app_actions(device_id=device_id, limit=limit, surface=surface, window_id=window_id)
        actions = result.get("actions") if isinstance(result, dict) else None
        if isinstance(actions, list) and actions:
            sumitalk_logger.info(
                "device_actions_poll device_id=%s surface=%s window_id=%s count=%s ids=%s types=%s",
                device_id,
                surface,
                window_id,
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
