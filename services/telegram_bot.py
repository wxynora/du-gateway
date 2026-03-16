# Telegram Bot 收发层：收用户消息 → 调网关 chat → 回复发回 Telegram
# 方案见 docs/主动发消息与Telegram完整方案.md；window_id 约定为 tg_{telegram_user_id}
import json
import logging
import time
from typing import Optional

import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_CHAT_MODEL,
    GATEWAY_MODELS,
)

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
# 长轮询超时（秒），期间有消息会立即返回
GET_UPDATES_TIMEOUT = 60


def _get_chat_model() -> str:
    """Bot 请求网关时使用的模型名。"""
    if TELEGRAM_CHAT_MODEL:
        return TELEGRAM_CHAT_MODEL
    if GATEWAY_MODELS:
        return GATEWAY_MODELS[0]
    return "gpt-4"


def _call_gateway_chat(window_id: str, user_text: str) -> Optional[str]:
    """
    调网关 /v1/chat/completions（非流式），返回 assistant 文本。
    window_id 应为 tg_{telegram_user_id}，以便与 RikkaHub 同套记忆/总结/动态层。
    """
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    body = {
        "model": _get_chat_model(),
        "messages": [{"role": "user", "content": user_text}],
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            logger.warning("网关返回非 200 status=%s body=%s", r.status_code, (r.text or "")[:500])
            return None
        data = r.json() if r.content else None
        if not data or "choices" not in data or not data["choices"]:
            logger.warning("网关响应无 choices: %s", (json.dumps(data)[:300] if data else "null"))
            return None
        msg = (data["choices"][0] or {}).get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        return content.strip() if isinstance(content, str) else str(content).strip()
    except requests.RequestException as e:
        logger.exception("请求网关失败: %s", e)
        return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("解析网关响应失败: %s", e)
        return None


def get_updates(offset: Optional[int] = None) -> dict:
    """拉取 Telegram 更新（长轮询）。"""
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": GET_UPDATES_TIMEOUT}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=GET_UPDATES_TIMEOUT + 10)
        if r.status_code != 200:
            logger.warning("getUpdates 非 200: %s %s", r.status_code, r.text[:200])
            return {}
        return r.json() or {}
    except requests.RequestException as e:
        logger.warning("getUpdates 请求异常: %s", e)
        return {}


def send_message(chat_id: int, text: str) -> bool:
    """向指定 chat 发送一条文字消息。"""
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            logger.warning("sendMessage 失败 chat_id=%s status=%s %s", chat_id, r.status_code, r.text[:200])
            return False
        return True
    except requests.RequestException as e:
        logger.warning("sendMessage 异常 chat_id=%s: %s", chat_id, e)
        return False


def send_message_to_user(telegram_user_id: int, text: str) -> bool:
    """
    向指定 Telegram 用户发消息（用于主动发消息等）。
    chat_id 与 user 私聊时等于 telegram_user_id。
    """
    return send_message(chat_id=telegram_user_id, text=text)


def process_message(chat_id: int, user_id: int, text: str) -> bool:
    """
    处理一条用户文字消息：调网关得到回复，发回 Telegram。
    user_id 用于 window_id = tg_{user_id}，保证同一用户同一窗口。
    返回是否成功发回回复。
    """
    window_id = f"tg_{user_id}"
    reply = _call_gateway_chat(window_id=window_id, user_text=text)
    if reply is None:
        reply = "暂时没连上渡，稍后再试哦～"
    return send_message(chat_id=chat_id, text=reply)


def run_polling():
    """
    长轮询循环：拉取更新 → 处理文字消息 → 调网关 → 发回回复。
    仅处理 text 消息；忽略其它类型（语音、图片等后续可接 STT/图像描述）。
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN 未配置，无法启动 Bot")
        return
    logger.info("Telegram Bot 开始轮询，网关=%s%s", TELEGRAM_GATEWAY_URL, TELEGRAM_CHAT_PATH)
    offset = None
    while True:
        try:
            data = get_updates(offset=offset)
            result = data.get("result") or []
            for upd in result:
                offset = (upd.get("update_id") or 0) + 1
                msg = upd.get("message")
                if not msg:
                    continue
                chat_id = msg.get("chat", {}).get("id")
                from_user = msg.get("from") or {}
                user_id = from_user.get("id")
                text = (msg.get("text") or "").strip()
                if not text:
                    # 后续可在此处理 voice/photo 等
                    continue
                if chat_id is None or user_id is None:
                    continue
                logger.info("收到 TG 消息 user_id=%s chat_id=%s len=%d", user_id, chat_id, len(text))
                process_message(chat_id=chat_id, user_id=user_id, text=text)
        except Exception as e:
            logger.exception("轮询处理异常: %s", e)
            time.sleep(5)
        if offset is None:
            time.sleep(1)
