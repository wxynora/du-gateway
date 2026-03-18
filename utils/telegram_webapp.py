import hmac
import hashlib
import time
import urllib.parse

from flask import abort, request

from config import (
    MINIAPP_INITDATA_MAX_AGE_SECONDS,
    MINIAPP_TELEGRAM_AUTH_ENABLED,
    TELEGRAM_BOT_TOKEN,
)

import logging

logger = logging.getLogger(__name__)


def _parse_init_data(init_data: str) -> dict[str, str]:
    # initData 是 querystring 格式（key=value&key2=value2），value 可能 urlencoded
    # Telegram 官方推荐用 parse_qsl
    items = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    return {k: v for k, v in items}


def _build_data_check_string(data: dict[str, str]) -> str:
    pairs = []
    for k in sorted(data.keys()):
        if k == "hash":
            continue
        pairs.append(f"{k}={data[k]}")
    return "\n".join(pairs)


def verify_telegram_init_data(init_data: str, bot_token: str) -> tuple[bool, str]:
    """
    校验 Telegram WebApp initData。
    规则：https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    init_data = (init_data or "").strip()
    bot_token = (bot_token or "").strip()
    if not init_data:
        return False, "缺少 initData"
    if not bot_token:
        return False, "TELEGRAM_BOT_TOKEN 未配置，无法校验 initData"

    data = _parse_init_data(init_data)
    their_hash = (data.get("hash") or "").strip()
    if not their_hash:
        return False, "initData 缺少 hash"

    # 时效校验（防复用）
    try:
        auth_date = int(data.get("auth_date") or "0")
    except Exception:
        auth_date = 0
    if auth_date > 0 and MINIAPP_INITDATA_MAX_AGE_SECONDS > 0:
        now = int(time.time())
        if now - auth_date > int(MINIAPP_INITDATA_MAX_AGE_SECONDS):
            return False, "initData 已过期，请在 Telegram 里重新打开"

    data_check_string = _build_data_check_string(data)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, their_hash):
        return False, "initData 校验失败（hash 不匹配）"
    return True, ""


def enforce_telegram_initdata():
    """用于 /miniapp-api/*：校验来自 Telegram Mini App 的请求。"""
    if not MINIAPP_TELEGRAM_AUTH_ENABLED:
        return

    # 兼容：优先 header，避免 URL 太长；其次 query/body（便于调试）
    init_data = (request.headers.get("X-Telegram-Init-Data") or "").strip()
    if not init_data:
        init_data = (request.args.get("initData") or "").strip()
    if not init_data and request.method in ("POST", "PUT", "PATCH"):
        data = request.get_json(silent=True) or {}
        init_data = (data.get("initData") or "").strip()

    ok, err = verify_telegram_init_data(init_data, TELEGRAM_BOT_TOKEN)
    if not ok:
        try:
            # 记录最关键的诊断信息（不打印完整 initData，避免泄露）
            src = "header" if (request.headers.get("X-Telegram-Init-Data") or "").strip() else ("query" if (request.args.get("initData") or "").strip() else "none")
            init_len = len(init_data or "")
            auth_date = 0
            try:
                auth_date = int(_parse_init_data(init_data).get("auth_date") or "0") if init_data else 0
            except Exception:
                auth_date = 0
            now = int(time.time())
            logger.warning(
                "MiniApp initData 校验失败 path=%s src=%s len=%s auth_date=%s now=%s max_age=%s err=%s",
                request.path,
                src,
                init_len,
                auth_date,
                now,
                int(MINIAPP_INITDATA_MAX_AGE_SECONDS or 0),
                err,
            )
        except Exception:
            pass
        abort(401, description=err or "Unauthorized")

