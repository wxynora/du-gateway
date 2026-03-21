# Telegram Bot 收发层：收用户消息 → 调网关 chat → 回复发回 Telegram
# 方案见 docs/主动发消息与Telegram完整方案.md；window_id 约定为 tg_{telegram_user_id}
import base64
import json
import logging
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_WEBAPP_URL,
    TELEGRAM_WEBAPP_VERSION,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_CHAT_MODEL,
    GATEWAY_MODELS,
    TELEGRAM_INPUT_IDLE_SECONDS,
    TELEGRAM_OUTPUT_CHUNK_CHARS,
    TELEGRAM_OUTPUT_SEND_DELAY_MIN_SECONDS,
    TELEGRAM_OUTPUT_SEND_DELAY_MAX_SECONDS,
    TELEGRAM_CONTEXT_LAST_TURNS,
    TELEGRAM_VOICE_REPLY_ENABLED,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
)

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
_RESOLVED_CHAT_MODEL: Optional[str] = None
_BUF_LOCK = threading.Lock()
_INPUT_BUFFERS: dict[int, dict] = {}
_CTX_LOCK = threading.Lock()
_CONTEXT_MESSAGES: dict[int, list[dict]] = {}

BTN_OPS_PANEL = "🛠 运维面板"
_AUTO_WEBAPP_VERSION: Optional[str] = None


def _resolve_webapp_version() -> str:
    """
    Telegram WebApp 版本号：
    - 优先用 TELEGRAM_WEBAPP_VERSION（手动配置）
    - 未配置时自动用 miniapp_static/index.html 的 mtime，静态包更新后会自动变化
    """
    manual = (TELEGRAM_WEBAPP_VERSION or "").strip()
    if manual:
        return manual
    global _AUTO_WEBAPP_VERSION
    if _AUTO_WEBAPP_VERSION is not None:
        return _AUTO_WEBAPP_VERSION
    try:
        p = Path(__file__).resolve().parent.parent / "miniapp_static" / "index.html"
        if p.exists():
            _AUTO_WEBAPP_VERSION = str(int(os.path.getmtime(p)))
            return _AUTO_WEBAPP_VERSION
    except Exception:
        pass
    _AUTO_WEBAPP_VERSION = ""
    return ""


def _miniapp_url() -> str:
    """ReplyKeyboard 的 WebApp 入口 URL（必须是公网可访问的完整 URL）。"""
    base = (TELEGRAM_WEBAPP_URL or "").strip().rstrip("/") or (TELEGRAM_GATEWAY_URL or "").strip().rstrip("/")
    if not base:
        return ""
    # Telegram WebApp 按钮强制要求 https，否则 sendMessage 会 400
    if not base.lower().startswith("https://"):
        return ""
    url = base + "/miniapp"
    v = _resolve_webapp_version()
    if v:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}v={v}"
    return url


def _ops_keyboard() -> dict:
    """常驻运维面板键盘（Reply Keyboard）。"""
    url = _miniapp_url()
    return {
        "keyboard": [
            (
                [{"text": BTN_OPS_PANEL, "web_app": {"url": url}}]
                if url
                else [{"text": "⚠️ 运维面板需要配置 HTTPS 域名"}]
            ),
        ],
        "resize_keyboard": True,
        # 一次性键盘：点击一次后自动收起，平时不占输入区；需要时用户可点输入框旁的键盘图标再展开
        "one_time_keyboard": True,
        "is_persistent": False,
    }


def _send_with_keyboard(chat_id: int, text: str) -> bool:
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "reply_markup": _ops_keyboard(), "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            logger.warning("sendMessage(键盘) 失败 chat_id=%s status=%s %s", chat_id, r.status_code, r.text[:200])
            return False
        data = r.json() if r.content else {}
        return bool(data.get("ok", True))
    except Exception as e:
        logger.warning("sendMessage(键盘) 异常 chat_id=%s: %s", chat_id, e)
        return False

# Telegram 端的输出风格约束（只影响 Telegram，不影响 RikkaHub）
_TELEGRAM_STYLE_SYSTEM = (
    "你正在通过 Telegram 和辛玥聊天。请遵守以下输出格式要求：\n"
    "1) 只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。\n"
    "2) 不要输出分割线（例如 ---、———、***）。\n"
    "3) 不要使用 Markdown 强调符号 * 或 **（Telegram 会显得很奇怪）。\n"
    "4) 不要输出“(表情包:xxx)”这类占位符；可以直接使用 emoji。\n"
    "5) 允许自然分段，但不要为了格式刻意堆很多空行。\n"
    "6) 你可以在想发语音的时候发语音：把想让她听到的那句话用 <voice>...</voice> 包起来（不要在里面写分割线或 *）。\n"
    "   - 你可以同时输出文字正文；Bot 会额外发送一条语音。\n"
    "   - 如果你不想发语音，就不要输出 <voice> 标签。\n"
)


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

    # 有换行：优先按换行切（短信感），避免渡一整段糊在一起
    if "\n" in t:
        out: list[str] = []

        def _flush_piece(piece: str):
            piece = (piece or "").strip()
            if not piece:
                return
            while len(piece) > max_len:
                out.append(piece[:max_len])
                piece = piece[max_len:].lstrip()
            if piece:
                out.append(piece)

        for line in t.split("\n"):
            line = line.strip()
            if not line:
                continue
            _flush_piece(line)
        return [x for x in (s.strip() for s in out) if x]

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


def _sanitize_reply_for_telegram(text: str) -> str:
    """
    Telegram 兜底清洗：
    - 去掉脑内OS段
    - 去掉分割线
    - 去掉星号（避免 Markdown）
    - 去掉 (表情包:xxx) 占位
    """
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")

    # 去掉 (表情包:xxx)
    t = re.sub(r"\(表情包:[^)]+\)", "", t)

    # 去掉分割线（整行 --- / *** / ——）
    t = re.sub(r"(?m)^\s*[-\*—]{3,}\s*$\n?", "", t)

    # 去掉脑内OS：从第一处“（脑内OS：”起，到遇到第一个空行或到文本末尾
    m = re.search(r"（\s*脑内OS\s*：", t)
    if m and m.start() <= 8:  # 只在开头附近触发，避免正文里提到“脑内OS”被误删
        after = t[m.start():]
        cut = re.split(r"\n\s*\n", after, maxsplit=1)
        if len(cut) == 2:
            t = (t[:m.start()] + cut[1]).lstrip()
        else:
            t = t[:m.start()].strip()

    # 去掉星号（避免 Markdown 强调）
    t = t.replace("*", "")

    # 收敛多空行
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def _extract_voice_tag(text: str) -> tuple[str, str]:
    """
    提取 <voice>...</voice>。
    返回 (clean_text, voice_text)。若没有则 voice_text=""。
    """
    if not text:
        return "", ""
    m = re.search(r"<voice>([\s\S]*?)</voice>", text, flags=re.IGNORECASE)
    if not m:
        return text, ""
    voice_text = (m.group(1) or "").strip()
    clean = (text[: m.start()] + text[m.end() :]).strip()
    # 收敛多空行
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, voice_text


def _trim_context_messages(msgs: list[dict]) -> list[dict]:
    """只保留最近 N 轮（每轮 user+assistant 两条）。"""
    n_turns = int(TELEGRAM_CONTEXT_LAST_TURNS or 0)
    if n_turns <= 0:
        return []
    max_msgs = n_turns * 2
    if len(msgs) <= max_msgs:
        return msgs
    return msgs[-max_msgs:]


def _bootstrap_context_from_r2(window_id: str) -> list[dict]:
    """
    当 Telegram 进程内上下文为空时，从 R2 的该窗口最近 N 轮回填 user/assistant 上下文，
    解决“Bot 侧 Last4 偶发为空（重启/波动后）”的问题。
    """
    try:
        from storage import r2_store
        rounds = r2_store.get_conversation_rounds(window_id, last_n=max(1, int(TELEGRAM_CONTEXT_LAST_TURNS or 4)))
    except Exception:
        rounds = []
    if not rounds:
        return []
    out: list[dict] = []
    for r in rounds:
        for m in (r.get("messages") or []):
            role = (m.get("role") or "").lower()
            if role not in ("user", "assistant"):
                continue
            content = m.get("content")
            if content is None:
                continue
            out.append({"role": role, "content": content})
    return _trim_context_messages(out)


def _normalize_user_content_to_parts(content: Union[str, list]) -> list[dict]:
    """把 user_content 归一化为多模态 parts（text/image_url）。"""
    if isinstance(content, str):
        t = content.strip()
        return [{"type": "text", "text": t}] if t else []
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict) and p.get("type"):
                out.append(p)
        return out
    return []


def _merge_user_contents(contents: list[Union[str, list]]) -> Union[str, list]:
    """
    合并多次用户输入：
    - 全是文本 -> 合并成一个字符串（按换行拼接）
    - 含多模态 -> 统一转 parts 列表
    """
    if not contents:
        return ""
    if all(isinstance(x, str) for x in contents):
        merged = "\n".join(str(x).strip() for x in contents if str(x).strip()).strip()
        return merged
    parts = []
    for c in contents:
        parts.extend(_normalize_user_content_to_parts(c))
    return parts


def _content_preview(content: Union[str, list], limit: int = 120) -> str:
    """把 Telegram 输入压成短预览，方便日志定位哪次请求失败。"""
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text":
                s = str(p.get("text") or "").strip()
                if s:
                    parts.append(s)
            elif p.get("type") == "image_url":
                parts.append("[image]")
        text = " ".join(parts).strip()
    else:
        text = str(content or "").strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _message_content_len(content) -> int:
    """粗略统计 message.content 长度，便于判断是否因为注入后过长。"""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text":
                total += len(str(p.get("text") or ""))
            elif p.get("type") == "image_url":
                total += len(str(((p.get("image_url") or {}).get("url")) or ""))
        return total
    return len(str(content or ""))


def _call_gateway_chat(window_id: str, user_id: int, user_content: Union[str, list], force_last4: bool = False) -> Optional[str]:
    """
    调网关 /v1/chat/completions（非流式），返回 assistant 文本。
    user_content 可为 str（纯文字）或 list（多模态，如 [{"type":"text","text":"..."},{"type":"image_url",...}]），与 RikkaHub 一致。
    """
    url = TELEGRAM_GATEWAY_URL.rstrip("/") + TELEGRAM_CHAT_PATH
    # 每次请求优先拉取网关当前可用模型（与 active upstream 同步），避免模型权限不匹配。
    # 拉取失败时再用本地解析逻辑兜底。
    model = _fetch_gateway_first_model() or _resolve_chat_model()

    with _CTX_LOCK:
        history = list(_CONTEXT_MESSAGES.get(user_id) or [])
        if not history:
            history = _bootstrap_context_from_r2(window_id)
            if history:
                _CONTEXT_MESSAGES[user_id] = list(history)
    history = _trim_context_messages(history)
    # Telegram 端增加一条风格 system（网关还会在最前面插入 du_core_prompt）
    messages = [{"role": "system", "content": _TELEGRAM_STYLE_SYSTEM}] + history + [{"role": "user", "content": user_content}]
    messages_chars = sum(_message_content_len(m.get("content")) for m in messages if isinstance(m, dict))
    user_chars = _message_content_len(user_content)
    history_turns = len(history) // 2
    user_preview = _content_preview(user_content)
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
    }
    if force_last4:
        headers["X-Force-Last4"] = "1"
    try:
        logger.info(
            "调用网关 chat window_id=%s user_id=%s model=%s force_last4=%s history_msgs=%s history_turns~=%s user_chars=%s messages_chars=%s preview=%s",
            window_id,
            user_id,
            model,
            force_last4,
            len(history),
            history_turns,
            user_chars,
            messages_chars,
            user_preview,
        )
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            preview = (r.text or "")[:500]
            lower = preview.lower()

            # 上游 403：常见原因是当前 token 没权限访问当前 model
            # 例：This token has no access to model xxx
            if r.status_code in (401, 403):
                # 注意：网关 body 可能不会透出上游原始错误文本，这里改成“兜底重试一次”。
                # 目标：当当前 model 与 active upstream 的 token 权限不匹配时，自动切到 active 可用的第一个模型。
                should_retry = ("no access to model" in lower) or ("token has no access to model" in lower)
                if not should_retry:
                    should_retry = True  # 兜底：只要 401/403，就尝试拉取网关可用模型重试一次

                new_model = _fetch_gateway_first_model() if should_retry else None
                if new_model and new_model != body.get("model"):
                    logger.warning(
                        "网关返回 %s：尝试切换 model=%s -> %s 并重试一次 preview=%s",
                        r.status_code,
                        body.get("model"),
                        new_model,
                        preview[:220],
                    )
                    body["model"] = new_model
                    r = requests.post(url, headers=headers, json=body, timeout=120)
            if r.status_code != 200:
                logger.warning(
                    "网关返回非 200 status=%s model=%s user_chars=%s messages_chars=%s preview=%s body=%s",
                    r.status_code,
                    body.get("model") or model,
                    user_chars,
                    messages_chars,
                    user_preview,
                    (r.text or "")[:500],
                )
                return None
        data = r.json() if r.content else None
        if not data or "choices" not in data or not data["choices"]:
            logger.warning(
                "网关响应无 choices model=%s user_chars=%s messages_chars=%s preview=%s resp=%s",
                body.get("model") or model,
                user_chars,
                messages_chars,
                user_preview,
                (json.dumps(data)[:300] if data else "null"),
            )
            return None
        msg = (data["choices"][0] or {}).get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        reply_text = content.strip() if isinstance(content, str) else str(content).strip()
        reply_text = _sanitize_reply_for_telegram(reply_text)
        # 更新上下文：只缓存 user/assistant（不存 system），下次请求自动带上
        with _CTX_LOCK:
            cur = list(_CONTEXT_MESSAGES.get(user_id) or [])
            cur.append({"role": "user", "content": user_content})
            cur.append({"role": "assistant", "content": reply_text})
            _CONTEXT_MESSAGES[user_id] = _trim_context_messages(cur)
        return reply_text
    except requests.RequestException as e:
        logger.exception("请求网关失败: %s", e)
        return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("解析网关响应失败: %s", e)
        return None


def _get_telegram_file_bytes(file_id: str) -> Optional[tuple[bytes, str]]:
    """
    通过 Telegram getFile 下载文件，返回 (bytes, mime_type)。
    用于图片等，mime 根据 file_path 后缀猜测，默认 image/jpeg。
    """
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/getFile"
    try:
        r = requests.get(url, params={"file_id": file_id}, timeout=15)
        if r.status_code != 200:
            logger.warning("getFile 非 200 file_id=%s %s", file_id[:20], r.text[:150])
            return None
        data = r.json() or {}
        if not data.get("ok"):
            return None
        path = (data.get("result") or {}).get("file_path") or ""
        if not path:
            return None
        # 注意：下载文件要走 /file/bot<TOKEN>/...，不是 /bot<TOKEN>/...
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{path}"
        r2 = requests.get(download_url, timeout=30)
        if r2.status_code != 200:
            logger.warning("下载 Telegram 文件失败 path=%s status=%s body=%s", path, r2.status_code, (r2.text or "")[:200])
            return None
        mime = "image/jpeg"
        if path.lower().endswith(".png"):
            mime = "image/png"
        elif path.lower().endswith(".gif"):
            mime = "image/gif"
        elif path.lower().endswith(".webp"):
            mime = "image/webp"
        return (r2.content, mime)
    except requests.RequestException as e:
        logger.warning("Telegram 获取文件异常 file_id=%s: %s", file_id[:20], e)
        return None


def _set_my_commands() -> bool:
    """清空 Bot 命令菜单。"""
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/setMyCommands"
    payload = {
        "commands": []
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            logger.warning("setMyCommands 非 200 status=%s body=%s", r.status_code, (r.text or "")[:200])
            return False
        data = r.json() if r.content else {}
        return bool(data.get("ok", True))
    except Exception as e:
        logger.warning("setMyCommands 失败: %s", e)
        return False


## 已移除：按钮式 Todo 便签（避免占用输入区交互与 R2 写入）


def send_message(chat_id: int, text: str) -> bool:
    """向指定 chat 发送一条文字消息。HTTP 200 时也检查 body 里 ok，避免 Telegram 返回 200 但未送达（如被拉黑）。"""
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            logger.warning("sendMessage 失败 chat_id=%s status=%s %s", chat_id, r.status_code, r.text[:200])
            return False
        try:
            data = r.json() if r.content else {}
        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            logger.warning("sendMessage 响应非 JSON chat_id=%s body_preview=%s err=%s", chat_id, (r.text or "")[:150], e)
            return False
        if not data.get("ok", True):
            logger.warning("sendMessage Telegram 未送达 chat_id=%s description=%s", chat_id, data.get("description", ""))
            return False
        logger.info("sendMessage 成功 chat_id=%s message_id=%s", chat_id, (data.get("result") or {}).get("message_id"))
        return True
    except requests.RequestException as e:
        logger.warning("sendMessage 异常 chat_id=%s: %s", chat_id, e)
        return False


def send_voice(chat_id: int, audio_bytes: bytes, filename: str = "voice.mp3") -> bool:
    """发送语音消息（Telegram sendVoice）。"""
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendVoice"
    try:
        files = {"voice": (filename, audio_bytes, "audio/mpeg")}
        data = {"chat_id": chat_id}
        r = requests.post(url, data=data, files=files, timeout=60)
        if r.status_code != 200:
            logger.warning("sendVoice 失败 chat_id=%s status=%s %s", chat_id, r.status_code, (r.text or "")[:200])
            return False
        return True
    except requests.RequestException as e:
        logger.warning("sendVoice 异常 chat_id=%s: %s", chat_id, e)
        return False


def send_chat_action(chat_id: int, action: str = "typing") -> bool:
    """发送 chat action（如 typing）用于“正在输入中…”指示器。"""
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendChatAction"
    payload = {"chat_id": chat_id, "action": action}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            logger.debug("sendChatAction 失败 chat_id=%s status=%s %s", chat_id, r.status_code, r.text[:120])
            return False
        return True
    except requests.RequestException:
        return False


def _start_typing_indicator(chat_id: int, stop_event: threading.Event, interval_seconds: float = 4.0):
    """
    轻量 typing：立即发一次；若 stop_event 未 set，则每 interval 再发一次。
    用于“调用网关等待回复”这段时间。
    """
    try:
        send_chat_action(chat_id=chat_id, action="typing")
        # 先等一会再重复（避免刷太频繁）
        while not stop_event.wait(max(1.0, float(interval_seconds))):
            send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        return


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


def process_message(
    chat_id: int,
    user_id: int,
    text: Optional[str] = None,
    user_content: Optional[list] = None,
    force_last4: bool = False,
) -> bool:
    """
    处理一条用户消息：调网关得到回复，发回 Telegram。
    text：纯文字时传入；user_content：多模态时传入（如 [{"type":"text",...},{"type":"image_url",...}]）。二者传一即可。
    """
    if user_content is not None:
        content: Union[str, list] = user_content
    elif text is not None:
        content = text
    else:
        return False
    window_id = f"tg_{user_id}"
    stop = threading.Event()
    t = threading.Thread(target=_start_typing_indicator, args=(int(chat_id), stop, 4.0), daemon=True)
    t.start()
    try:
        reply = _call_gateway_chat(window_id=window_id, user_id=user_id, user_content=content, force_last4=force_last4)
    finally:
        stop.set()
    if reply is None:
        reply = "暂时没连上渡，稍后再试哦～"
    # 解析语音标签
    reply_clean, voice_text = _extract_voice_tag(reply)
    reply_clean = _sanitize_reply_for_telegram(reply_clean)

    # 先发文字（短信分段）
    ok_text = send_message_segmented(chat_id=chat_id, text=reply_clean) if reply_clean else True

    # 再按需发语音
    if TELEGRAM_VOICE_REPLY_ENABLED and voice_text:
        try:
            from services.minimax_tts import tts_to_audio_bytes

            audio = tts_to_audio_bytes(voice_text)
            if audio:
                send_chat_action(chat_id=int(chat_id), action="record_voice")
                send_voice(chat_id=int(chat_id), audio_bytes=audio, filename="du.mp3")
        except Exception:
            pass
    return ok_text


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


def _append_user_part_locked(chat_id: int, user_id: int, part: dict):
    """在 lock 内追加一个多模态 part（text/image_url）。"""
    buf = _INPUT_BUFFERS.get(user_id)
    if not buf:
        buf = {"chat_id": chat_id, "parts": [], "timer": None, "flush_at": None}
        _INPUT_BUFFERS[user_id] = buf
    buf["chat_id"] = chat_id
    buf.setdefault("parts", []).append(part)


def append_user_input(chat_id: int, user_id: int, text: str):
    """
    输入聚合：把同一 user 的多条短消息先缓存，停输入 N 秒后合并成一条再调网关。
    """
    if not text:
        return
    t = text.strip()
    if not t:
        return
    with _BUF_LOCK:
        _append_user_part_locked(chat_id, user_id, {"type": "text", "text": t})
        # 统一走输入缓冲聚合，避免长消息绕过缓存导致上下文不连续。
        _schedule_flush_locked(user_id)


def flush_user_buffer(user_id: int):
    """把缓存的用户输入（多模态 parts）合并成一条，调用网关并回复（分段发送）。"""
    with _BUF_LOCK:
        buf = _INPUT_BUFFERS.get(user_id)
        if not buf:
            return
        chat_id = buf.get("chat_id")
        parts = buf.get("parts") or []
        buf["parts"] = []
        t: Optional[threading.Timer] = buf.get("timer")
        buf["timer"] = None
        buf["flush_at"] = None
        if t:
            try:
                t.cancel()
            except Exception:
                pass
        # 空则直接返回
        if not parts:
            return
        # 没有 chat_id 也不处理
        if chat_id is None:
            return

    # 合并连续 text part，减少 token 与噪声
    merged_parts = []
    text_acc = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            s = str(p.get("text") or "").strip()
            if s:
                text_acc.append(s)
            continue
        # 非 text：先 flush 累积文本
        if text_acc:
            merged_parts.append({"type": "text", "text": "\n".join(text_acc).strip()})
            text_acc = []
        merged_parts.append(p)
    if text_acc:
        merged_parts.append({"type": "text", "text": "\n".join(text_acc).strip()})

    merged_parts = [p for p in merged_parts if isinstance(p, dict) and p.get("type")]
    if not merged_parts:
        return
    logger.info("输入聚合 flush user_id=%s chat_id=%s parts=%d", user_id, chat_id, len(merged_parts))
    process_message(chat_id=int(chat_id), user_id=user_id, user_content=merged_parts)


def init_telegram_bot_runtime():
    """在服务启动时调用：初始化命令菜单等。Webhook 模式下无需轮询。"""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN 未配置，Telegram 功能将不可用")
        return
    _set_my_commands()


def handle_telegram_update(upd: dict):
    """处理一条 Telegram update（供 webhook 与轮询共用）。"""
    msg = (upd or {}).get("message") or (upd or {}).get("edited_message")
    if not msg:
        return
    chat_id = msg.get("chat", {}).get("id")
    from_user = msg.get("from") or {}
    user_id = from_user.get("id")
    if chat_id is None or user_id is None:
        return

    text = (msg.get("text") or "").strip()
    caption = (msg.get("caption") or "").strip()

    # 图片（带或不带 caption）→ 追加到聚合缓冲
    if (not text) and msg.get("photo"):
        photos = msg.get("photo") or []
        if not photos:
            return
        largest = max(photos, key=lambda p: (p.get("width") or 0) * (p.get("height") or 0))
        file_id = largest.get("file_id")
        if not file_id:
            send_message(chat_id, "图片没拿到 file_id，再发一次试试～")
            return
        file_result = _get_telegram_file_bytes(file_id)
        if not file_result:
            send_message(chat_id, "图片下载失败，稍后再试哦～")
            return
        img_bytes, mime = file_result
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        if TELEGRAM_PROACTIVE_TARGET_USER_ID and user_id == TELEGRAM_PROACTIVE_TARGET_USER_ID:
            from utils.time_aware import now_beijing_iso
            from storage import r2_store
            r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
        logger.info("收到 TG 图片(聚合) user_id=%s chat_id=%s caption_len=%d", user_id, chat_id, len(caption))
        with _BUF_LOCK:
            _append_user_part_locked(chat_id, user_id, {"type": "text", "text": caption or "[图片]"})
            _append_user_part_locked(chat_id, user_id, {"type": "image_url", "image_url": {"url": data_url}})
            _schedule_flush_locked(user_id)
        return

    if not text:
        return

    # /start：弹出运维面板键盘（不进入聊天）
    cmd0 = (text.strip().split()[0] if text else "").split("@", 1)[0].lower()
    if cmd0 == "/start":
        _send_with_keyboard(int(chat_id), "运维面板键盘已就绪。需要做什么？")
        return

    logger.info("收到 TG 消息 user_id=%s chat_id=%s len=%d", user_id, chat_id, len(text))
    if TELEGRAM_PROACTIVE_TARGET_USER_ID and user_id == TELEGRAM_PROACTIVE_TARGET_USER_ID:
        from utils.time_aware import now_beijing_iso
        from storage import r2_store
        r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
    append_user_input(chat_id=chat_id, user_id=user_id, text=text)
