# Telegram Bot 收发层：收用户消息 → 调网关 chat → 回复发回 Telegram
# 方案见 docs/主动发消息与Telegram完整方案.md；window_id 约定为 tg_{telegram_user_id}
import json
import logging
import random
import threading
import time
from typing import Optional

import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_CHAT_MODEL,
    GATEWAY_MODELS,
    TELEGRAM_INPUT_IDLE_SECONDS,
    TELEGRAM_INPUT_IMMEDIATE_CHARS,
    TELEGRAM_OUTPUT_CHUNK_CHARS,
    TELEGRAM_OUTPUT_SEND_DELAY_MIN_SECONDS,
    TELEGRAM_OUTPUT_SEND_DELAY_MAX_SECONDS,
    TELEGRAM_CONTEXT_LAST_TURNS,
)

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
# 长轮询超时（秒），期间有消息会立即返回
GET_UPDATES_TIMEOUT = 60
_RESOLVED_CHAT_MODEL: Optional[str] = None
_BUF_LOCK = threading.Lock()
_INPUT_BUFFERS: dict[int, dict] = {}
_CTX_LOCK = threading.Lock()
_CONTEXT_MESSAGES: dict[int, list[dict]] = {}


def _fetch_gateway_first_model() -> Optional[str]:
    """
    从网关 /v1/models 拉取第一个模型 id，作为 Bot 的默认模型。
    注意：网关会把该接口代理到上游（或用 GATEWAY_MODELS 兜底）。
    """
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + "/v1/models"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            logger.warning("网关 /v1/models 非 200 status=%s body=%s", r.status_code, (r.text or "")[:200])
            return None
        data = r.json() if r.content else None
        lst = (data or {}).get("data") or []
        if not lst:
            return None
        first = lst[0]
        if isinstance(first, dict) and first.get("id"):
            return str(first["id"]).strip()
        if isinstance(first, str) and first.strip():
            return first.strip()
        return None
    except Exception as e:
        logger.warning("拉取网关模型列表失败: %s", e)
        return None


def _resolve_chat_model() -> str:
    """
    解析 Bot 请求网关时使用的模型名。
    优先级：
    1) TELEGRAM_CHAT_MODEL（显式配置）
    2) 网关 /v1/models 第一个
    3) GATEWAY_MODELS 第一个（静态兜底）
    4) gpt-4（最后兜底：仅在上游兼容该字符串时才可用）
    """
    global _RESOLVED_CHAT_MODEL
    if _RESOLVED_CHAT_MODEL:
        return _RESOLVED_CHAT_MODEL
    if TELEGRAM_CHAT_MODEL and TELEGRAM_CHAT_MODEL.strip():
        _RESOLVED_CHAT_MODEL = TELEGRAM_CHAT_MODEL.strip()
        return _RESOLVED_CHAT_MODEL
    m = _fetch_gateway_first_model()
    if m:
        _RESOLVED_CHAT_MODEL = m
        return _RESOLVED_CHAT_MODEL
    if GATEWAY_MODELS:
        _RESOLVED_CHAT_MODEL = GATEWAY_MODELS[0]
        return _RESOLVED_CHAT_MODEL
    _RESOLVED_CHAT_MODEL = "gpt-4"
    return _RESOLVED_CHAT_MODEL


def _sleep_between_sends():
    a = TELEGRAM_OUTPUT_SEND_DELAY_MIN_SECONDS
    b = TELEGRAM_OUTPUT_SEND_DELAY_MAX_SECONDS
    if b <= 0:
        return
    if a < 0:
        a = 0
    if b < a:
        a, b = b, a
    time.sleep(random.uniform(a, b))


def _split_reply_text(text: str) -> list[str]:
    """
    将回复拆成多条发回 Telegram，避免一次性超长。
    规则：
    - 先把「很多短段落」尽量合并到接近上限（避免渡爱换行导致太碎）
    - 段落过长时，再按中英文句末标点切
    - 最后按 TELEGRAM_OUTPUT_CHUNK_CHARS 做硬截断（Telegram 单条上限 4096）
    """
    if not text:
        return []
    max_len = int(TELEGRAM_OUTPUT_CHUNK_CHARS or 1500)
    if max_len <= 0:
        max_len = 1500

    # 归一化换行
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not t:
        return []

    paras = [p.strip() for p in t.split("\n\n") if p.strip()]
    out: list[str] = []
    seps = set("。！？.!?")

    def _flush_piece(piece: str):
        piece = (piece or "").strip()
        if not piece:
            return
        # 硬切
        while len(piece) > max_len:
            out.append(piece[:max_len])
            piece = piece[max_len:].lstrip()
        if piece:
            out.append(piece)

    def _split_long_para(p: str):
        buf = ""
        for ch in p:
            buf += ch
            if ch in seps and len(buf) >= max_len * 0.6:
                _flush_piece(buf)
                buf = ""
        if buf:
            _flush_piece(buf)

    # 先尽量合并小段落，减少「一换行就一条」的碎片
    acc = ""
    for p in paras:
        if not acc:
            # acc 为空，直接放入（若很长，后面处理）
            if len(p) > max_len:
                _split_long_para(p)
                acc = ""
            else:
                acc = p
            continue

        sep = "\n\n"
        if len(acc) + len(sep) + len(p) <= max_len:
            acc = acc + sep + p
            continue

        # acc 放不下了，先 flush acc
        _flush_piece(acc)
        acc = ""

        # 再处理当前段落
        if len(p) > max_len:
            _split_long_para(p)
        else:
            acc = p

    if acc:
        _flush_piece(acc)

    # 兜底去空
    return [x for x in (s.strip() for s in out) if x]


def _trim_context_messages(msgs: list[dict]) -> list[dict]:
    """只保留最近 N 轮（每轮 user+assistant 两条）。"""
    n_turns = int(TELEGRAM_CONTEXT_LAST_TURNS or 0)
    if n_turns <= 0:
        return []
    max_msgs = n_turns * 2
    if len(msgs) <= max_msgs:
        return msgs
    return msgs[-max_msgs:]


def _call_gateway_chat(window_id: str, user_id: int, user_text: str) -> Optional[str]:
    """
    调网关 /v1/chat/completions（非流式），返回 assistant 文本。
    window_id 应为 tg_{telegram_user_id}，以便与 RikkaHub 同套记忆/总结/动态层。
    """
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    model = _resolve_chat_model()

    with _CTX_LOCK:
        history = list(_CONTEXT_MESSAGES.get(user_id) or [])
    history = _trim_context_messages(history)
    messages = history + [{"role": "user", "content": user_text}]
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            logger.warning(
                "网关返回非 200 status=%s model=%s body=%s",
                r.status_code,
                model,
                (r.text or "")[:500],
            )
            return None
        data = r.json() if r.content else None
        if not data or "choices" not in data or not data["choices"]:
            logger.warning("网关响应无 choices: %s", (json.dumps(data)[:300] if data else "null"))
            return None
        msg = (data["choices"][0] or {}).get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        reply_text = content.strip() if isinstance(content, str) else str(content).strip()
        # 更新上下文：只缓存 user/assistant（不存 system），下次请求自动带上
        with _CTX_LOCK:
            cur = list(_CONTEXT_MESSAGES.get(user_id) or [])
            cur.append({"role": "user", "content": user_text})
            cur.append({"role": "assistant", "content": reply_text})
            _CONTEXT_MESSAGES[user_id] = _trim_context_messages(cur)
        return reply_text
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


def send_message_segmented(chat_id: int, text: str) -> bool:
    """把一段长文本拆成多条发回 Telegram（带间隔）。"""
    parts = _split_reply_text(text)
    if not parts:
        return send_message(chat_id=chat_id, text=text or "")
    ok_any = False
    for i, part in enumerate(parts):
        ok = send_message(chat_id=chat_id, text=part)
        ok_any = ok_any or ok
        # 最后一条不 sleep
        if i != len(parts) - 1:
            _sleep_between_sends()
    return ok_any


def process_message(chat_id: int, user_id: int, text: str) -> bool:
    """
    处理一条用户文字消息：调网关得到回复，发回 Telegram。
    user_id 用于 window_id = tg_{user_id}，保证同一用户同一窗口。
    返回是否成功发回回复。
    """
    window_id = f"tg_{user_id}"
    reply = _call_gateway_chat(window_id=window_id, user_id=user_id, user_text=text)
    if reply is None:
        reply = "暂时没连上渡，稍后再试哦～"
    return send_message_segmented(chat_id=chat_id, text=reply)


def _schedule_flush_locked(user_id: int):
    """在 lock 内为该 user 安排一次 flush（取消旧 timer）。"""
    buf = _INPUT_BUFFERS.get(user_id)
    if not buf:
        return
    t: Optional[threading.Timer] = buf.get("timer")
    if t:
        try:
            t.cancel()
        except Exception:
            pass
    delay = float(TELEGRAM_INPUT_IDLE_SECONDS or 30)
    if delay < 0.5:
        delay = 0.5
    timer = threading.Timer(delay, flush_user_buffer, args=(user_id,))
    timer.daemon = True
    buf["timer"] = timer
    buf["flush_at"] = time.time() + delay
    timer.start()


def append_user_input(chat_id: int, user_id: int, text: str):
    """
    输入聚合：把同一 user 的多条短消息先缓存，停输入 N 秒后合并成一条再调网关。
    - 超过 TELEGRAM_INPUT_IMMEDIATE_CHARS 的长消息：立即 flush（不等停输入）
    """
    if not text:
        return
    t = text.strip()
    if not t:
        return
    immediate_chars = int(TELEGRAM_INPUT_IMMEDIATE_CHARS or 200)
    if immediate_chars < 0:
        immediate_chars = 0

    with _BUF_LOCK:
        buf = _INPUT_BUFFERS.get(user_id)
        if not buf:
            buf = {"chat_id": chat_id, "messages": [], "timer": None, "flush_at": None}
            _INPUT_BUFFERS[user_id] = buf
        buf["chat_id"] = chat_id
        buf["messages"].append(t)
        # 长消息直接 flush（减少等待）
        if immediate_chars and len(t) >= immediate_chars:
            # 取消定时器，异步 flush
            if buf.get("timer"):
                try:
                    buf["timer"].cancel()
                except Exception:
                    pass
                buf["timer"] = None
            threading.Thread(target=flush_user_buffer, args=(user_id,), daemon=True).start()
            return
        _schedule_flush_locked(user_id)


def flush_user_buffer(user_id: int):
    """把缓存的用户输入合并成一条，调用网关并回复（分段发送）。"""
    with _BUF_LOCK:
        buf = _INPUT_BUFFERS.get(user_id)
        if not buf:
            return
        chat_id = buf.get("chat_id")
        msgs = buf.get("messages") or []
        buf["messages"] = []
        t: Optional[threading.Timer] = buf.get("timer")
        buf["timer"] = None
        buf["flush_at"] = None
        if t:
            try:
                t.cancel()
            except Exception:
                pass
        # 空则直接返回
        if not msgs:
            return
        # 没有 chat_id 也不处理
        if chat_id is None:
            return

    merged = "\n".join(msgs).strip()
    if not merged:
        return
    logger.info("输入聚合 flush user_id=%s chat_id=%s merged_parts=%d len=%d", user_id, chat_id, len(msgs), len(merged))
    process_message(chat_id=int(chat_id), user_id=user_id, text=merged)


def run_polling():
    """
    长轮询循环：拉取更新 → 处理文字消息 → 调网关 → 发回回复。
    仅处理 text 消息；忽略其它类型（语音、图片等后续可接 STT/图像描述）。
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN 未配置，无法启动 Bot")
        return
    model = _resolve_chat_model()
    logger.info("Telegram Bot 开始轮询，网关=%s%s model=%s", TELEGRAM_GATEWAY_URL, TELEGRAM_CHAT_PATH, model)
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
                append_user_input(chat_id=chat_id, user_id=user_id, text=text)
        except Exception as e:
            logger.exception("轮询处理异常: %s", e)
            time.sleep(5)
        if offset is None:
            time.sleep(1)
