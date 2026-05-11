from flask import Blueprint, request, jsonify

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_GM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET
from services.telegram_update_queue import enqueue_update, summarize_update
from utils.log import get_logger

logger = get_logger(__name__)
bp = Blueprint("telegram_webhook", __name__)


def _webhook_check_secret():
    """若配置了 TELEGRAM_WEBHOOK_SECRET，则校验 Telegram 发来的 X-Telegram-Bot-Api-Secret-Token。"""
    if TELEGRAM_WEBHOOK_SECRET:
        tok = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if tok != TELEGRAM_WEBHOOK_SECRET:
            return jsonify({"ok": False, "error": "invalid_secret"}), 401
    return None


@bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """
    主 Bot Webhook：私聊渡、运维 /start 等（与文游 GM Bot 分离时勿将文游群指令指向本 Bot）。
    """
    err = _webhook_check_secret()
    if err:
        return err
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "main_bot_not_configured"}), 503

    update = request.get_json(silent=True) or {}
    try:
        result = enqueue_update(update, bot_kind="main")
    except Exception as e:
        logger.exception("Telegram webhook 持久队列写入失败 bot=main: %s", e)
        return jsonify({"ok": False, "error": "webhook_queue_error"}), 503
    logger.info(
        "Telegram webhook 已落持久队列 bot=main queued=%s duplicate=%s key=%s %s",
        result.enqueued,
        result.duplicate,
        result.update_key,
        summarize_update(update),
    )
    return jsonify({"ok": True, "queued": result.enqueued, "duplicate": result.duplicate})


@bp.route("/telegram/webhook_gm", methods=["POST"])
def telegram_webhook_gm():
    """
    文游专用 GM Bot Webhook：仅处理文游固定群内 /story /go /end 与玩家行动（需配置 TELEGRAM_GM_BOT_TOKEN）。
    """
    err = _webhook_check_secret()
    if err:
        return err
    if not TELEGRAM_GM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "gm_bot_not_configured"}), 404

    update = request.get_json(silent=True) or {}
    try:
        result = enqueue_update(update, bot_kind="gm")
    except Exception as e:
        logger.exception("Telegram webhook 持久队列写入失败 bot=gm: %s", e)
        return jsonify({"ok": False, "error": "webhook_queue_error"}), 503
    logger.info(
        "Telegram webhook 已落持久队列 bot=gm queued=%s duplicate=%s key=%s %s",
        result.enqueued,
        result.duplicate,
        result.update_key,
        summarize_update(update),
    )
    return jsonify({"ok": True, "queued": result.enqueued, "duplicate": result.duplicate})


"""
注意：不要在 Blueprint 上使用 before_app_first_request（不同 Flask 版本可能不存在）。
Webhook 只负责快速落持久队列；Telegram 运行时由 scripts/run_telegram_webhook_worker.py 常驻进程持有。
"""
