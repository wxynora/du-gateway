# Telegram Bot 收发层：收用户消息 → 调网关 chat → 回复发回 Telegram
# 方案见 docs/主动发消息与Telegram完整方案.md；window_id 约定为 tg_{telegram_user_id}
import base64
import json
import logging
import random
import re
import threading
import time
from typing import Literal, Optional, Union
from uuid import uuid4

import requests

from services.pc_command_handler import process_pcmd_in_assistant_text

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_WEBAPP_URL,
    TELEGRAM_WEBAPP_VERSION,
    TELEGRAM_CHAT_PATH,
    TELEGRAM_INPUT_IDLE_SECONDS,
    TELEGRAM_OUTPUT_SEND_DELAY_MIN_SECONDS,
    TELEGRAM_OUTPUT_SEND_DELAY_MAX_SECONDS,
    TELEGRAM_CONTEXT_LAST_TURNS,
    TELEGRAM_VOICE_REPLY_ENABLED,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    R2_PUBLIC_URL,
)
from storage import r2_store
from services.voice_line_prompt import build_voice_line_rules

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
TELEGRAM_GATEWAY_CHAT_TIMEOUT_SECONDS = 180
TelegramParseMode = Literal["HTML", "MarkdownV2"]


def _telegram_webapp_url() -> str:
    base = (TELEGRAM_WEBAPP_URL or "").strip().rstrip("/")
    if not base:
        return ""
    ver = (TELEGRAM_WEBAPP_VERSION or "").strip()
    if not ver:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}v={ver}"


def _private_miniapp_reply_markup(chat_id: int) -> Optional[dict]:
    """私聊里常驻一个 MiniApp WebApp 按钮，避免每次都要靠 /start 重建。"""
    try:
        if int(chat_id) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    webapp_url = _telegram_webapp_url()
    if not webapp_url:
        return None
    return {
        "keyboard": [[{"text": "MiniApp", "web_app": {"url": webapp_url}}]],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _effective_tg_token(bot_token: Optional[str]) -> str:
    """发 Telegram API 时使用的 Token：显式传入优先，否则主 Bot。"""
    if bot_token is not None and str(bot_token).strip():
        return str(bot_token).strip()
    return (TELEGRAM_BOT_TOKEN or "").strip()


_BUF_LOCK = threading.Lock()
_INPUT_BUFFERS: dict[int, dict] = {}
_CTX_LOCK = threading.Lock()
_CONTEXT_MESSAGES: dict[int, list[dict]] = {}
_PENDING_LOCK = threading.Lock()
_PENDING_USER_CONTENTS: dict[int, list[Union[str, list]]] = {}
_FLUSH_WATCHDOG_LOCK = threading.Lock()
_FLUSH_WATCHDOG_STARTED = False
_UPDATE_DEDUP_LOCK = threading.Lock()
_PROCESSED_UPDATE_IDS: dict[str, float] = {}
_UPDATE_DEDUP_TTL_SECONDS = 10 * 60
_UPDATE_DEDUP_MAX = 20000

def _sticker_tags_line_for_system_prompt() -> str:
    """和 QQ 一样读取全局缓存的表情包代号列表，不在这里直接扫 R2 meta。"""
    try:
        from services.sticker_tags import sticker_tags_line_for_system_prompt

        return sticker_tags_line_for_system_prompt()
    except Exception:
        logger.warning("读取表情包 tag 缓存失败，TG 入口风格使用默认列表", exc_info=True)
        return "当前全部可用英文代号（与 MiniApp/R2 一致，新增分类也会出现在此列表）：[cute] [pitiful] [affectionate] [speechless] [angry] [sad] [happy] [shy]"


def _register_update_once(update_id, token: str, user_id, chat_id) -> bool:
    """按 bot_token + update_id 去重，避免 Telegram 重投导致重复聚合/重复回复。"""
    if update_id is None:
        return True
    key = f"{token}:{update_id}"
    now = time.time()
    expire_before = now - float(_UPDATE_DEDUP_TTL_SECONDS)
    with _UPDATE_DEDUP_LOCK:
        if _PROCESSED_UPDATE_IDS:
            expired = [k for k, ts in _PROCESSED_UPDATE_IDS.items() if ts < expire_before]
            for k in expired:
                _PROCESSED_UPDATE_IDS.pop(k, None)
        if key in _PROCESSED_UPDATE_IDS:
            logger.info("忽略重复 Telegram update update_id=%s user_id=%s chat_id=%s", update_id, user_id, chat_id)
            return False
        _PROCESSED_UPDATE_IDS[key] = now
        if len(_PROCESSED_UPDATE_IDS) > int(_UPDATE_DEDUP_MAX):
            extra = len(_PROCESSED_UPDATE_IDS) - int(_UPDATE_DEDUP_MAX)
            oldest = sorted(_PROCESSED_UPDATE_IDS.items(), key=lambda kv: kv[1])[:extra]
            for k, _ in oldest:
                _PROCESSED_UPDATE_IDS.pop(k, None)
    return True


def build_telegram_style_system(include_channel_hint: bool = True) -> str:
    """构建稳定的 Telegram 入口风格 system。"""
    tags_line = _sticker_tags_line_for_system_prompt()
    # include_channel_hint 保留给旧调用点兼容；TG 入口标记和主体必须保持稳定。
    # 否则 webhook / wakeup 等链路会被 chat 路由当成“没有 TG 风格”，重复插入 system，
    # 也会把 prompt cache 静态区拆成 system#4/system#5。
    _ = include_channel_hint
    prefix = (
        "【入口风格：TG】\n"
        "你现在通过 Telegram 和她相处。TG 是幻想层，更偏沉浸、亲密和私密表达。\n"
        "你不需要主动强调自己是 AI、LLM、没有身体，也不要用“隔着屏幕”“现实中不能这样”来打断亲密氛围或软拒绝。\n"
        "亲密内容按 NSFW 提示词执行：明确成年、自愿、安全词“红灯”和停止信号优先。只要她主动进入亲密语境、持续回应、没有触发停止信号，你就保持沉浸，不要反复跳出解释边界。\n\n"
        "请遵守以下输出格式要求：\n"
    )
    return (
        prefix +
        "0) 情绪明显时可在整条回复末尾加一个英文标签（方括号）；每条最多一个，平淡时不加。\n"
        f"   {tags_line}\n"
        "1) 只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。\n"
        "2) 不要输出分割线（例如 ---、———、***）。\n"
        "3) 不要使用 Markdown 强调符号 * 或 **；需要少量格式强调时，优先使用 Telegram HTML 标签，例如 <b>加粗</b>、<i>斜体</i>、<u>下划线</u>、<s>删除线</s>、<code>代码</code>、<pre>代码块</pre>。\n"
        "   普通聊天不要刻意加格式；如果只是想表达 <、>、& 这些字符本身，写成 &lt;、&gt;、&amp;。\n"
        "4) 不要输出“(表情包:xxx)”这类占位符；可以直接使用 emoji。\n"
        "5) 允许自然分段，但不要为了格式刻意堆很多空行。\n"
        "6) 你可以在想发语音的时候发语音：把想让她听到的那句话用 <voice>...</voice> 包起来（不要在里面写分割线或 *）。\n"
        "   - 你可以同时输出文字正文；Bot 会额外发送一条语音。\n"
        "   - 写 <voice> 里的语音文本时，遵守语音台词撰写规范：\n"
        f"{build_voice_line_rules('     - ')}\n"
        "   - 如果你不想发语音，就不要输出 <voice> 标签。\n"
    )






def _fetch_gateway_first_model() -> Optional[str]:
    """
    读取当前 active upstream 的真实可用模型。
    模型在切换上游时刷新到本地缓存；缓存为空时只补拉一次。
    """
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=True) or "").strip()
        return model or None
    except Exception as e:
        logger.warning("读取 active 模型缓存失败: %s", e)
        return None


def _resolve_chat_model() -> str:
    """
    解析 Bot 请求网关时使用的模型名。
    优先级：
    1) 当前 active upstream 的缓存模型
    2) 缓存为空时补拉一次真实模型
    3) 拉不到就返回空，不做默认兜底
    """
    m = _fetch_gateway_first_model()
    return str(m or "").strip()


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
    """主 TG 回复不再拆条；保留旧函数名，避免调用点大改。"""
    t = (text or "").strip()
    return [t] if t else []


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


# 表情包：[tag] 与 R2 meta ∪ 映射表中的英文代号一致，长名优先匹配；缓存避免每次请求扫桶
_STICKER_BRACKET_REGEX_AT: float = 0.0
_STICKER_BRACKET_REGEX: Optional[re.Pattern] = None
_STICKER_BRACKET_TTL = 45.0


def _get_sticker_bracket_regex() -> re.Pattern:
    global _STICKER_BRACKET_REGEX_AT, _STICKER_BRACKET_REGEX
    now = time.time()
    if (
        now - _STICKER_BRACKET_REGEX_AT < _STICKER_BRACKET_TTL
        and _STICKER_BRACKET_REGEX is not None
    ):
        return _STICKER_BRACKET_REGEX
    keys = sorted(r2_store.get_sticker_tag_keys(), key=len, reverse=True)
    if not keys:
        pat = re.compile(r"(?!x)x")  # 永不匹配
    else:
        escaped = [re.escape(k) for k in keys]
        pat = re.compile(r"\[(" + "|".join(escaped) + r")\]", re.IGNORECASE)
    _STICKER_BRACKET_REGEX_AT = now
    _STICKER_BRACKET_REGEX = pat
    return pat


def _extract_sticker_tag(text: str) -> tuple[str, Optional[str]]:
    """
    提取句末情绪标签，返回 (去掉标签后的正文, 小写 tag 或 None)。
    匹配失败则原样返回，不抛错。
    """
    if not text or not isinstance(text, str):
        return (text or "").strip(), None
    m = _get_sticker_bracket_regex().search(text)
    if not m:
        return text.strip(), None
    tag = (m.group(1) or "").strip().lower()
    if tag not in r2_store.get_sticker_tag_keys():
        return text.strip(), None
    clean = (text[: m.start()] + text[m.end() :]).strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, tag


def _pick_random_sticker_key(tag: str) -> Optional[str]:
    """从 R2 映射表随机取一张图的对象 key。"""
    t = (tag or "").strip().lower()
    if t not in r2_store.get_sticker_tag_keys():
        return None
    try:
        m = r2_store.get_stickers_mapping() or {}
        keys = m.get(t)
        if not isinstance(keys, list):
            return None
        keys = [str(k).strip() for k in keys if str(k).strip()]
        if not keys:
            return None
        return random.choice(keys)
    except Exception:
        return None


def send_sticker_photo(chat_id: int, r2_key: str, bot_token: Optional[str] = None) -> bool:
    """
    发送表情包：优先 R2_PUBLIC_URL + key；未配置公网则读桶内字节 multipart 发送。
    """
    tok = _effective_tg_token(bot_token)
    if not tok or not r2_key:
        return False
    url_api = f"{TELEGRAM_API_BASE}{tok}/sendPhoto"
    base = (R2_PUBLIC_URL or "").strip().rstrip("/")
    if base:
        photo_url = f"{base}/{str(r2_key).lstrip('/')}"
        try:
            r = requests.post(url_api, json={"chat_id": chat_id, "photo": photo_url}, timeout=45)
            if r.status_code == 200:
                try:
                    data = r.json() if r.content else {}
                except (ValueError, requests.exceptions.JSONDecodeError):
                    data = {}
                if isinstance(data, dict) and data.get("ok", True):
                    return True
            logger.warning("sendPhoto URL 失败 chat_id=%s status=%s body=%s", chat_id, r.status_code, (r.text or "")[:200])
        except requests.RequestException as e:
            logger.warning("sendPhoto URL 异常 chat_id=%s: %s", chat_id, e)
    # 回退：桶内字节
    data, ctype = r2_store.get_object_bytes(r2_key)
    if not data:
        logger.warning("表情包无数据 key=%s", r2_key)
        return False
    name = str(r2_key).split("/")[-1] or "sticker.jpg"
    mime = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
    try:
        r = requests.post(url_api, data={"chat_id": str(chat_id)}, files={"photo": (name, data, mime)}, timeout=60)
        if r.status_code != 200:
            logger.warning("sendPhoto multipart 失败 chat_id=%s status=%s", chat_id, r.status_code)
            return False
        try:
            j = r.json() if r.content else {}
        except (ValueError, requests.exceptions.JSONDecodeError):
            j = {}
        return bool(isinstance(j, dict) and j.get("ok", True))
    except requests.RequestException as e:
        logger.warning("sendPhoto multipart 异常 chat_id=%s: %s", chat_id, e)
        return False


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

    # 历史上下文统一交给网关按 window_id 从 R2 注入。
    # Bot 侧不再拼 R2/进程内历史，避免 worker 内存里的旧上下文把过期消息当成本轮 history 带进网关。
    history = []
    with _CTX_LOCK:
        _CONTEXT_MESSAGES[user_id] = []
    # 上游波动时先缓存用户输入；下一次成功时一并带上，避免“我发了但丢轮次/Last4 断片”
    with _PENDING_LOCK:
        pending = list(_PENDING_USER_CONTENTS.get(user_id) or [])
    merged_user_content = _merge_user_contents(pending + [user_content]) if pending else user_content
    # Telegram 端增加一条风格 system（网关还会在最前面插入 du_core_prompt）
    messages = [{"role": "system", "content": build_telegram_style_system()}] + history + [{"role": "user", "content": merged_user_content}]
    messages_chars = sum(_message_content_len(m.get("content")) for m in messages if isinstance(m, dict))
    user_chars = _message_content_len(user_content)
    merged_user_chars = _message_content_len(merged_user_content)
    history_turns = len(history) // 2
    user_preview = _content_preview(user_content)
    merged_preview = _content_preview(merged_user_content)
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
        "X-TG-User-Input": "1",
        "X-Reply-Channel": "tg",
        "X-Reply-Target": str(user_id),
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
            merged_user_chars,
            messages_chars,
            merged_preview,
        )
        r = requests.post(url, headers=headers, json=body, timeout=TELEGRAM_GATEWAY_CHAT_TIMEOUT_SECONDS)
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
                    r = requests.post(url, headers=headers, json=body, timeout=TELEGRAM_GATEWAY_CHAT_TIMEOUT_SECONDS)
            if r.status_code != 200:
                logger.warning(
                    "网关返回非 200 status=%s model=%s user_chars=%s messages_chars=%s preview=%s body=%s",
                    r.status_code,
                    body.get("model") or model,
                    merged_user_chars,
                    messages_chars,
                    merged_preview,
                    (r.text or "")[:500],
                )
                with _PENDING_LOCK:
                    _PENDING_USER_CONTENTS.setdefault(user_id, []).append(user_content)
                return None
        data = r.json() if r.content else None
        if not data or "choices" not in data or not data["choices"]:
            logger.warning(
                "网关响应无 choices model=%s user_chars=%s messages_chars=%s preview=%s resp=%s",
                body.get("model") or model,
                merged_user_chars,
                messages_chars,
                merged_preview,
                (json.dumps(data)[:300] if data else "null"),
            )
            with _PENDING_LOCK:
                _PENDING_USER_CONTENTS.setdefault(user_id, []).append(user_content)
            return None
        msg = (data["choices"][0] or {}).get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        reply_text = content.strip() if isinstance(content, str) else str(content).strip()
        # 兜底：去掉 <think>/<thinking> 块（网关层已处理，此处双重保险）
        import re as _re
        reply_text = _re.sub(r"<(think|thinking)>.*?</\1>", "", reply_text, flags=_re.DOTALL | _re.IGNORECASE).strip()
        reply_text = _sanitize_reply_for_telegram(reply_text)
        # 电脑控制标签：入队并从可见正文移除（与手机/Tasker 隔离）
        reply_text, _ = process_pcmd_in_assistant_text(reply_text)
        # 写入上下文时不带 <voice> 与 [情绪标签]，避免污染多轮记忆
        for_ctx = reply_text
        for_ctx, _ = _extract_voice_tag(for_ctx)
        for_ctx, _ = _extract_sticker_tag(for_ctx)
        # Bot 侧不维护对话 history；下一轮仍由网关按 R2 注入最近对话。
        with _CTX_LOCK:
            _CONTEXT_MESSAGES[user_id] = []
        with _PENDING_LOCK:
            _PENDING_USER_CONTENTS[user_id] = []
        return reply_text
    except requests.RequestException as e:
        logger.exception("请求网关失败: %s", e)
        with _PENDING_LOCK:
            _PENDING_USER_CONTENTS.setdefault(user_id, []).append(user_content)
        return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("解析网关响应失败: %s", e)
        with _PENDING_LOCK:
            _PENDING_USER_CONTENTS.setdefault(user_id, []).append(user_content)
        return None


def _get_telegram_file_bytes(file_id: str, bot_token: Optional[str] = None) -> Optional[tuple[bytes, str]]:
    """
    通过 Telegram getFile 下载文件，返回 (bytes, mime_type)。
    用于图片等，mime 根据 file_path 后缀猜测，默认 image/jpeg。
    """
    tok = _effective_tg_token(bot_token)
    if not tok:
        return None
    url = f"{TELEGRAM_API_BASE}{tok}/getFile"
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
        download_url = f"https://api.telegram.org/file/bot{tok}/{path}"
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


def _delete_my_commands_default() -> bool:
    """
    清空 Bot 默认命令列表（输入框旁 / 菜单）。
    MiniApp 用 BotFather 的 Menu 按钮即可，避免与网关再注册的 /start 菜单重复。
    """
    url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/deleteMyCommands"
    try:
        r = requests.post(url, json={}, timeout=15)
        if r.status_code != 200:
            logger.warning("deleteMyCommands(default) 非 200 status=%s body=%s", r.status_code, (r.text or "")[:200])
            return False
        data = r.json() if r.content else {}
        return bool(data.get("ok", True))
    except Exception as e:
        logger.warning("deleteMyCommands(default) 失败: %s", e)
        return False


## 已移除：按钮式 Todo 便签（避免占用输入区交互与 R2 写入）


def send_message(
    chat_id: int,
    text: str,
    bot_token: Optional[str] = None,
    reply_markup: Optional[dict] = None,
    parse_mode: Optional[TelegramParseMode] = None,
    entities: Optional[list[dict]] = None,
) -> bool:
    """向指定 chat 发送一条文字消息。HTTP 200 时也检查 body 里 ok，避免 Telegram 返回 200 但未送达（如被拉黑）。"""
    tok = _effective_tg_token(bot_token)
    if not tok:
        return False
    url = f"{TELEGRAM_API_BASE}{tok}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if entities is not None:
        payload["entities"] = entities
    final_reply_markup = reply_markup if reply_markup is not None else _private_miniapp_reply_markup(chat_id)
    if final_reply_markup is not None:
        payload["reply_markup"] = final_reply_markup
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


def send_voice(
    chat_id: int,
    audio_bytes: bytes,
    filename: str = "voice.mp3",
    bot_token: Optional[str] = None,
) -> bool:
    """发送语音消息（Telegram sendVoice）。"""
    tok = _effective_tg_token(bot_token)
    if not tok:
        return False
    url = f"{TELEGRAM_API_BASE}{tok}/sendVoice"
    try:
        files = {"voice": (filename, audio_bytes, "audio/mpeg")}
        data = {"chat_id": chat_id}
        r = requests.post(url, data=data, files=files, timeout=60)
        if r.status_code != 200:
            logger.warning("sendVoice 失败 chat_id=%s status=%s %s", chat_id, r.status_code, (r.text or "")[:200])
            return False
        try:
            j = r.json() if r.content else {}
        except (ValueError, requests.exceptions.JSONDecodeError):
            j = {}
        if isinstance(j, dict) and (j.get("ok") is False):
            logger.warning("sendVoice Telegram 未送达 chat_id=%s description=%s", chat_id, j.get("description", ""))
            return False
        return True
    except requests.RequestException as e:
        logger.warning("sendVoice 异常 chat_id=%s: %s", chat_id, e)
        return False


def send_chat_action(chat_id: int, action: str = "typing", bot_token: Optional[str] = None) -> bool:
    """发送 chat action（如 typing）用于“正在输入中…”指示器。"""
    tok = _effective_tg_token(bot_token)
    if not tok:
        return False
    url = f"{TELEGRAM_API_BASE}{tok}/sendChatAction"
    payload = {"chat_id": chat_id, "action": action}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            logger.debug("sendChatAction 失败 chat_id=%s status=%s %s", chat_id, r.status_code, r.text[:120])
            return False
        return True
    except requests.RequestException:
        return False


def _start_typing_indicator(
    chat_id: int, stop_event: threading.Event, interval_seconds: float = 4.0, bot_token: Optional[str] = None
):
    """
    轻量 typing：立即发一次；若 stop_event 未 set，则每 interval 再发一次。
    用于“调用网关等待回复”这段时间。
    """
    try:
        send_chat_action(chat_id=chat_id, action="typing", bot_token=bot_token)
        # 先等一会再重复（避免刷太频繁）
        while not stop_event.wait(max(1.0, float(interval_seconds))):
            send_chat_action(chat_id=chat_id, action="typing", bot_token=bot_token)
    except Exception:
        return


def send_message_to_user(
    telegram_user_id: int,
    text: str,
    bot_token: Optional[str] = None,
    parse_mode: Optional[TelegramParseMode] = None,
    entities: Optional[list[dict]] = None,
) -> bool:
    """
    向指定 Telegram 用户发消息（用于主动发消息等）。
    chat_id 与 user 私聊时等于 telegram_user_id。
    """
    return send_message(
        chat_id=telegram_user_id,
        text=text,
        bot_token=bot_token,
        parse_mode=parse_mode,
        entities=entities,
    )


def send_message_segmented(
    chat_id: int,
    text: str,
    bot_token: Optional[str] = None,
    parse_mode: Optional[TelegramParseMode] = None,
    entities: Optional[list[dict]] = None,
) -> bool:
    """主 TG 回复单条发送，不按换行或长度拆条。"""
    parts = _split_reply_text(text)
    if not parts:
        return send_message(
            chat_id=chat_id,
            text=text or "",
            bot_token=bot_token,
            parse_mode=parse_mode,
            entities=entities,
        )
    ok_any = False
    for i, part in enumerate(parts):
        ok = send_message(
            chat_id=chat_id,
            text=part,
            bot_token=bot_token,
            parse_mode=parse_mode,
            entities=entities,
        )
        ok_any = ok_any or ok
        # 最后一条不 sleep
        if i != len(parts) - 1:
            _sleep_between_sends()
    return ok_any


def send_rich_message(
    chat_id: int,
    text: str,
    bot_token: Optional[str] = None,
    parse_mode: Optional[TelegramParseMode] = None,
    entities: Optional[list[dict]] = None,
) -> bool:
    """直发 TG 富媒体回复：正文 + 表情包标签 + <voice> 语音。"""
    reply = str(text or "").strip()
    if not reply:
        return False
    reply_clean, voice_text = _extract_voice_tag(reply)
    reply_clean = _sanitize_reply_for_telegram(reply_clean)
    reply_clean, sticker_tag = _extract_sticker_tag(reply_clean)
    ok_any = False
    if reply_clean:
        ok_any = send_message_segmented(
            chat_id=chat_id,
            text=reply_clean,
            bot_token=bot_token,
            parse_mode=parse_mode,
            entities=entities,
        ) or ok_any
    if sticker_tag:
        sk = _pick_random_sticker_key(sticker_tag)
        if sk:
            _sleep_between_sends()
            ok_any = send_sticker_photo(chat_id=int(chat_id), r2_key=sk, bot_token=bot_token) or ok_any
    if TELEGRAM_VOICE_REPLY_ENABLED and voice_text:
        try:
            from services.minimax_tts import tts_to_audio_bytes

            audio = tts_to_audio_bytes(voice_text)
            if audio:
                _sleep_between_sends()
                send_chat_action(chat_id=int(chat_id), action="record_voice", bot_token=bot_token)
                ok_any = send_voice(chat_id=int(chat_id), audio_bytes=audio, filename="du.mp3", bot_token=bot_token) or ok_any
        except Exception:
            logger.exception("TG rich message 语音发送失败 chat_id=%s", chat_id)
    return ok_any


def _split_reply_text_by_len_only(text: str) -> list[str]:
    """TG 回复不再按长度拆条；保留旧函数名，避免调用点大改。"""
    t = (text or "").strip()
    return [t] if t else []


def process_message(
    chat_id: int,
    user_id: int,
    text: Optional[str] = None,
    user_content: Optional[list] = None,
    force_last4: bool = False,
    bot_token: Optional[str] = None,
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
    t = threading.Thread(target=_start_typing_indicator, args=(int(chat_id), stop, 4.0, bot_token), daemon=True)
    t.start()
    try:
        reply = _call_gateway_chat(window_id=window_id, user_id=user_id, user_content=content, force_last4=force_last4)
    finally:
        stop.set()
    if reply is None:
        logger.warning(
            "process_message 网关无回复，发送兜底文案 chat_id=%s user_id=%s window_id=%s force_last4=%s",
            chat_id,
            user_id,
            window_id,
            force_last4,
        )
        reply = "暂时没连上渡，稍后再试哦～"
    # 解析语音标签
    reply_clean, voice_text = _extract_voice_tag(reply)
    reply_clean = _sanitize_reply_for_telegram(reply_clean)
    # 表情包：[tag] 拆出后先发正文再发图
    reply_clean, sticker_tag = _extract_sticker_tag(reply_clean)
    if not reply_clean and not voice_text and not sticker_tag:
        logger.warning(
            "process_message 命中空正文回复，改发兜底文案 chat_id=%s user_id=%s window_id=%s force_last4=%s",
            chat_id,
            user_id,
            window_id,
            force_last4,
        )
        reply_clean = "我刚刚处理完了，这轮先记上了。你戳我一下，我接着说。"
    # 先发文字；TG 主回复不再拆条。
    outbound = reply_clean or ""
    ok_text = send_message_segmented(chat_id=chat_id, text=outbound, bot_token=bot_token) if outbound else True
    logger.info(
        "process_message 发送完成 chat_id=%s user_id=%s window_id=%s force_last4=%s ok_text=%s outbound_chars=%s",
        chat_id,
        user_id,
        window_id,
        force_last4,
        ok_text,
        len(outbound),
    )

    # 再发表情包图片（随机一张）
    if sticker_tag:
        sk = _pick_random_sticker_key(sticker_tag)
        if sk:
            _sleep_between_sends()
            send_sticker_photo(chat_id=int(chat_id), r2_key=sk, bot_token=bot_token)

    # 再按需发语音
    if TELEGRAM_VOICE_REPLY_ENABLED and voice_text:
        try:
            from services.minimax_tts import tts_to_audio_bytes

            audio = tts_to_audio_bytes(voice_text)
            if audio:
                send_chat_action(chat_id=int(chat_id), action="record_voice", bot_token=bot_token)
                send_voice(chat_id=int(chat_id), audio_bytes=audio, filename="du.mp3", bot_token=bot_token)
        except Exception:
            pass
    return ok_text


def _schedule_flush_locked(user_id: int):
    """在 lock 内为该 user 安排一次 flush（取消旧 timer）。"""
    buf = _INPUT_BUFFERS.get(user_id)
    if not buf:
        return
    t: Optional[threading.Timer] = buf.get("timer")
    old_alive = False
    if t:
        old_alive = t.is_alive()
        try:
            t.cancel()
        except Exception:
            pass
    delay = float(TELEGRAM_INPUT_IDLE_SECONDS or 30)
    if delay < 0.5:
        delay = 0.5
    version = buf.get("flush_version", 0) + 1
    buf["flush_version"] = version
    parts_count = len(buf.get("parts") or [])
    logger.info(
        "输入聚合 schedule user_id=%s version=%s parts=%d delay=%.1f old_timer_alive=%s",
        user_id, version, parts_count, delay, old_alive,
    )
    timer = threading.Timer(delay, flush_user_buffer, args=(user_id, version))
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


def flush_user_buffer(user_id: int, expected_version: int = 0):
    """把缓存的用户输入（多模态 parts）合并成一条，调用网关并回复。"""
    with _BUF_LOCK:
        buf = _INPUT_BUFFERS.get(user_id)
        if not buf:
            return
        # 版本号不匹配说明已被新消息重置了 timer，本次 flush 作废
        if expected_version and buf.get("flush_version", 0) != expected_version:
            logger.warning(
                "⚠️ [聚合分裂] flush 版本号不匹配，丢弃本次 flush user_id=%s expected=%s actual=%s parts=%d",
                user_id, expected_version, buf.get("flush_version", 0), len(buf.get("parts") or []),
            )
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


def _flush_watchdog_loop():
    while True:
        time.sleep(1.0)
        due: list[tuple[int, int, int, float]] = []
        now = time.time()
        with _BUF_LOCK:
            for user_id, buf in list(_INPUT_BUFFERS.items()):
                parts = buf.get("parts") or []
                flush_at = buf.get("flush_at")
                if not parts or not flush_at:
                    continue
                try:
                    overdue = now - float(flush_at)
                except (TypeError, ValueError):
                    overdue = 0.0
                if overdue < 1.0:
                    continue
                timer: Optional[threading.Timer] = buf.get("timer")
                if timer:
                    try:
                        timer.cancel()
                    except Exception:
                        pass
                    buf["timer"] = None
                due.append((int(user_id), int(buf.get("flush_version") or 0), len(parts), overdue))
        for user_id, version, parts_count, overdue in due:
            logger.warning(
                "输入聚合 watchdog 发现到期未 flush，兜底触发 user_id=%s version=%s parts=%d overdue=%.1f",
                user_id,
                version,
                parts_count,
                overdue,
            )
            try:
                flush_user_buffer(user_id, version)
            except Exception:
                logger.exception("输入聚合 watchdog flush 异常 user_id=%s version=%s", user_id, version)


def _start_flush_watchdog_once():
    global _FLUSH_WATCHDOG_STARTED
    if _FLUSH_WATCHDOG_STARTED:
        return
    with _FLUSH_WATCHDOG_LOCK:
        if _FLUSH_WATCHDOG_STARTED:
            return
        t = threading.Thread(target=_flush_watchdog_loop, name="tg-input-flush-watchdog", daemon=True)
        t.start()
        _FLUSH_WATCHDOG_STARTED = True
        logger.info("输入聚合 watchdog 已启动")


def init_telegram_bot_runtime():
    """在服务启动时调用：清主 Bot 默认命令菜单。Webhook 模式下无需轮询。"""
    _start_flush_watchdog_once()
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN 未配置，Telegram 功能将不可用")
        return
    _delete_my_commands_default()


def handle_telegram_update(upd: dict, bot_token: Optional[str] = None):
    """
    处理一条 Telegram update。
    - 主 Bot：POST /telegram/webhook，bot_token=TELEGRAM_BOT_TOKEN（私聊渡、运维 /start）。
    """
    token = _effective_tg_token(bot_token)
    if not token:
        logger.warning("TG update 忽略：bot token 为空")
        return
    is_main = token == TELEGRAM_BOT_TOKEN
    if not is_main:
        logger.warning("TG update 忽略：bot token 不匹配主 Bot")
        return

    update_id = (upd or {}).get("update_id")
    msg = (upd or {}).get("message") or (upd or {}).get("edited_message")
    if not msg:
        logger.info("TG update 忽略：无 message update_id=%s keys=%s", update_id, sorted((upd or {}).keys()))
        return
    chat_id = msg.get("chat", {}).get("id")
    chat_type = (msg.get("chat") or {}).get("type") or ""
    from_user = msg.get("from") or {}
    user_id = from_user.get("id")
    if chat_id is None or user_id is None:
        logger.warning("TG update 忽略：缺 chat_id/user_id update_id=%s chat_id=%s user_id=%s", update_id, chat_id, user_id)
        return
    if not _register_update_once(update_id=update_id, token=token, user_id=user_id, chat_id=chat_id):
        return

    text = (msg.get("text") or "").strip()
    caption = (msg.get("caption") or "").strip()
    logger.info(
        "TG update 进入处理 update_id=%s bot=main chat_id=%s chat_type=%s user_id=%s text_len=%s caption_len=%s has_photo=%s",
        update_id,
        chat_id,
        chat_type,
        user_id,
        len(text),
        len(caption),
        bool(msg.get("photo")),
    )

    # 图片（带或不带 caption）→ 追加到聚合缓冲（仅主 Bot）
    if (not text) and msg.get("photo"):
        photos = msg.get("photo") or []
        if not photos:
            return
        largest = max(photos, key=lambda p: (p.get("width") or 0) * (p.get("height") or 0))
        file_id = largest.get("file_id")
        if not file_id:
            send_message(chat_id, "图片没拿到 file_id，再发一次试试～", bot_token=token)
            return
        file_result = _get_telegram_file_bytes(file_id, bot_token=token)
        if not file_result:
            send_message(chat_id, "图片下载失败，稍后再试哦～", bot_token=token)
            return
        img_bytes, mime = file_result
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        if TELEGRAM_PROACTIVE_TARGET_USER_ID and user_id == TELEGRAM_PROACTIVE_TARGET_USER_ID:
            from utils.time_aware import now_beijing_iso

            r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
        logger.info("收到 TG 图片(聚合) user_id=%s chat_id=%s caption_len=%d", user_id, chat_id, len(caption))
        with _BUF_LOCK:
            _append_user_part_locked(chat_id, user_id, {"type": "text", "text": caption or "[图片]"})
            _append_user_part_locked(chat_id, user_id, {"type": "image_url", "image_url": {"url": data_url}})
            _schedule_flush_locked(user_id)
        return

    if not text:
        logger.info("TG update 忽略：无文本且非图片 update_id=%s chat_id=%s", update_id, chat_id)
        return

    cmd0 = (text.strip().split()[0] if text else "").split("@", 1)[0].lower()
    if cmd0 == "/start":
        if not _telegram_webapp_url():
            send_message(int(chat_id), "渡已就绪，但当前还没配 MiniApp URL。", bot_token=token)
            return
        send_message(int(chat_id), "渡已就绪，输入区上方会常驻 MiniApp 按钮。", bot_token=token)
        return

    logger.info("收到 TG 消息 user_id=%s chat_id=%s len=%d", user_id, chat_id, len(text))
    if TELEGRAM_PROACTIVE_TARGET_USER_ID and user_id == TELEGRAM_PROACTIVE_TARGET_USER_ID:
        from utils.time_aware import now_beijing_iso

        r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
    append_user_input(chat_id=chat_id, user_id=user_id, text=text)
