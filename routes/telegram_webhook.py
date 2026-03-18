import threading

from flask import Blueprint, request, jsonify

from config import TELEGRAM_WEBHOOK_SECRET
from utils.log import get_logger

logger = get_logger(__name__)
bp = Blueprint("telegram_webhook", __name__)


@bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """
    Telegram Webhook 更新入口：
    - 立即返回 200，后台异步处理 update，避免 Telegram 超时重试
    - 可选校验 secret_token（X-Telegram-Bot-Api-Secret-Token）
    """
    if TELEGRAM_WEBHOOK_SECRET:
        tok = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if tok != TELEGRAM_WEBHOOK_SECRET:
            return jsonify({"ok": False, "error": "invalid_secret"}), 401

    update = request.get_json(silent=True) or {}

    def _work(u: dict):
        try:
            from services.telegram_bot import handle_telegram_update

            handle_telegram_update(u)
        except Exception as e:
            logger.exception("处理 Telegram webhook update 失败: %s", e)

    t = threading.Thread(target=_work, args=(update,))
    t.daemon = True
    t.start()
    return jsonify({"ok": True})


@bp.before_app_first_request
def _init_bot():
    """进程启动后初始化 Telegram 运行时（命令菜单等）。"""
    try:
        from services.telegram_bot import init_telegram_bot_runtime

        init_telegram_bot_runtime()
    except Exception:
        return

