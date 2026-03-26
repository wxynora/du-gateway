# Telegram Bot 收发层：收用户消息 → 调网关 chat → 回复发回 Telegram
# 方案见 docs/主动发消息与Telegram完整方案.md；window_id 约定为 tg_{telegram_user_id}
import base64
import json
import logging
import random
import re
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

import requests

from services.wenyou_service import (
    cmd_end,
    cmd_go,
    cmd_settle,
    cmd_story,
    record_group_player2_line,
    record_group_player_line,
)
from services.pc_command_handler import process_pcmd_in_assistant_text

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_GM_BOT_TOKEN,
    TELEGRAM_GATEWAY_URL,
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
    WENYOU_GROUP_CHAT_ID,
    TELEGRAM_WENYOU_OWNER_USER_ID,
    R2_PUBLIC_URL,
    TELEGRAM_STICKER_MAX_EDGE,
    TELEGRAM_STICKER_JPEG_QUALITY,
    TELEGRAM_STICKER_MAX_BYTES_BEFORE_RECOMPRESS,
    TELEGRAM_STICKER_CANVAS_EDGE,
)
from storage import r2_store

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def _is_wenyou_active() -> bool:
    """是否存在进行中的文游局（按文游群 chat_id 会话）。"""
    gid = int(WENYOU_GROUP_CHAT_ID or 0)
    if gid == 0:
        return False
    try:
        s = r2_store.get_wenyou_session(gid)
        return bool(isinstance(s, dict) and s.get("gameId"))
    except Exception:
        return False


def _get_main_bot_telegram_user_id() -> Optional[int]:
    """缓存主 Bot 的 id（与群内发言 from.id 对齐）。"""
    global _MAIN_BOT_TELEGRAM_USER_ID
    if _MAIN_BOT_TELEGRAM_USER_ID is not None:
        return _MAIN_BOT_TELEGRAM_USER_ID
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        r = requests.get(f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/getMe", timeout=15)
        data = r.json() if r.content else {}
        if data.get("ok") and isinstance(data.get("result"), dict):
            bid = (data.get("result") or {}).get("id")
            if bid is not None:
                _MAIN_BOT_TELEGRAM_USER_ID = int(bid)
                return _MAIN_BOT_TELEGRAM_USER_ID
    except Exception:
        pass
    return None


def _is_message_from_main_bot(msg: dict) -> bool:
    """是否为当前主 Bot 在群内发的消息（渡作为玩家二发言）。"""
    fr = msg.get("from") or {}
    if not fr.get("is_bot"):
        return False
    mid = _get_main_bot_telegram_user_id()
    if mid is None:
        return False
    try:
        return int(fr.get("id") or 0) == int(mid)
    except (TypeError, ValueError):
        return False


def _effective_tg_token(bot_token: Optional[str]) -> str:
    """发 Telegram API 时使用的 Token：显式传入优先，否则主 Bot。"""
    if bot_token is not None and str(bot_token).strip():
        return str(bot_token).strip()
    return (TELEGRAM_BOT_TOKEN or "").strip()
_RESOLVED_CHAT_MODEL: Optional[str] = None
# 主 Bot 的 Telegram user id（getMe.id），用于识别群内「渡」的发言
_MAIN_BOT_TELEGRAM_USER_ID: Optional[int] = None
_BUF_LOCK = threading.Lock()
_INPUT_BUFFERS: dict[int, dict] = {}
_CTX_LOCK = threading.Lock()
_CONTEXT_MESSAGES: dict[int, list[dict]] = {}
_PENDING_LOCK = threading.Lock()
_PENDING_USER_CONTENTS: dict[int, list[Union[str, list]]] = {}

# Telegram 端的输出风格约束（只影响 Telegram）；表情包代号行从 R2 meta 动态生成，见 build_telegram_style_system
_STICKER_SYS_LINE_CACHE_AT: float = 0.0
_STICKER_SYS_LINE_CACHE_TEXT: str = ""


def _sticker_tags_line_for_system_prompt() -> str:
    """从 stickers/meta.json 读出当前全部英文代号，让模型知道 MiniApp 里有哪些分类。"""
    global _STICKER_SYS_LINE_CACHE_AT, _STICKER_SYS_LINE_CACHE_TEXT
    now = time.time()
    if now - _STICKER_SYS_LINE_CACHE_AT < 45.0 and _STICKER_SYS_LINE_CACHE_TEXT:
        return _STICKER_SYS_LINE_CACHE_TEXT
    try:
        meta = r2_store.get_stickers_meta()
        keys: list[str] = []
        for it in meta.get("tags") or []:
            if isinstance(it, dict) and it.get("key"):
                k = str(it["key"]).strip().lower()
                if k:
                    keys.append(k)
        if not keys:
            keys = sorted(r2_store.get_sticker_tag_keys())
        if not keys:
            text = "（暂无表情包分类元数据；可在 MiniApp 里添加分类后再用句末 [tag]。）"
        else:
            listed = " ".join(f"[{k}]" for k in keys)
            text = f"当前全部可用英文代号（与 MiniApp/R2 一致，新增分类也会出现在此列表）：{listed}"
    except Exception:
        text = "表情包英文代号以 MiniApp 配置为准；句末可加小写 [tag]。"
    _STICKER_SYS_LINE_CACHE_AT = now
    _STICKER_SYS_LINE_CACHE_TEXT = text
    return text


def build_telegram_style_system() -> str:
    """每次请求网关前调用，使渡掌握最新表情包分类列表。"""
    tags_line = _sticker_tags_line_for_system_prompt()
    return (
        "你正在通过 Telegram 和辛玥聊天。请遵守以下输出格式要求：\n"
        "0) 情绪明显时可在整条回复末尾加一个英文标签（方括号）；每条最多一个，平淡时不加。\n"
        f"   {tags_line}\n"
        "1) 只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。\n"
        "2) 不要输出分割线（例如 ---、———、***）。\n"
        "3) 不要使用 Markdown 强调符号 * 或 **（Telegram 会显得很奇怪）。\n"
        "4) 不要输出“(表情包:xxx)”这类占位符；可以直接使用 emoji。\n"
        "5) 允许自然分段，但不要为了格式刻意堆很多空行。\n"
        "6) 你可以在想发语音的时候发语音：把想让她听到的那句话用 <voice>...</voice> 包起来（不要在里面写分割线或 *）。\n"
        "   - 你可以同时输出文字正文；Bot 会额外发送一条语音。\n"
        "   - 如果你不想发语音，就不要输出 <voice> 标签。\n"
        "7) 如需控制电脑，可在整条回复里最多追加一个 [PCMD:...] 标签；不确定就不要加。\n"
        "   - 仅允许这些指令：\n"
        "     [PCMD:lock] 锁屏\n"
        "     [PCMD:shutdown] 关机（默认 60 秒后）\n"
        "     [PCMD:shutdown:秒数] 定时关机（0-86400）\n"
        "     [PCMD:restart] 重启（默认 60 秒后）\n"
        "     [PCMD:restart:秒数] 定时重启（0-86400）\n"
        "     [PCMD:sleep] 睡眠\n"
        "     [PCMD:mute] 静音\n"
        "     [PCMD:volume:0-100] 设置音量（整数）\n"
        "     [PCMD:notify:标题:内容] 电脑通知\n"
        "     [PCMD:open:notepad] 打开记事本\n"
        "     [PCMD:open:notepad:要写入的内容] 打开记事本并预填内容\n"
        "     [PCMD:open:chrome] 打开 Chrome\n"
        "     [PCMD:open:vscode] 打开 VS Code\n"
        "     [PCMD:open:wechat] 打开微信\n"
        "     [PCMD:open:notion] 打开 Notion\n"
        "     [PCMD:url:https://... ] 打开网页（仅 https）\n"
        "     [PCMD:media:play] 播放/暂停媒体\n"
        "   - 严禁输出未列出的 PCMD；若不确定，请不要输出 PCMD。\n"
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


def _letterbox_sticker_on_canvas(im, canvas_side: int):
    """
    将已缩小的图贴在正方形透明画布中心（边距透明，自定义聊天背景可透出）。
    无 Alpha 的 JPG 等会先转成不透明 RGBA 再贴到透明底。Telegram sendPhoto 是否保留透明取决于客户端。
    """
    from PIL import Image

    if canvas_side <= 0:
        return im
    im = im.copy()
    if im.mode == "P":
        im = im.convert("RGBA") if "transparency" in im.info else im.convert("RGB").convert("RGBA")
    elif im.mode == "LA":
        im = im.convert("RGBA")
    elif im.mode == "RGB":
        im = im.convert("RGBA")
    elif im.mode != "RGBA":
        im = im.convert("RGB").convert("RGBA")
    if max(im.size) > canvas_side:
        im.thumbnail((canvas_side, canvas_side), Image.Resampling.LANCZOS)
    cw, ch = im.size
    if cw <= 0 or ch <= 0:
        return im
    ox = (canvas_side - cw) // 2
    oy = (canvas_side - ch) // 2
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    canvas.paste(im, (ox, oy), im)
    return canvas


def _sticker_pil_to_send_bytes(im, stem: str, quality: int) -> tuple[bytes, str, str]:
    """将 PIL 图像编码为 Telegram 可发的 bytes（透明→PNG，否则 JPEG）。"""
    out = BytesIO()
    q = min(95, max(50, int(quality)))
    if im.mode == "P":
        im = im.convert("RGBA") if "transparency" in im.info else im.convert("RGB")
    if im.mode in ("RGBA", "LA"):
        if im.mode == "LA":
            im = im.convert("RGBA")
        im.save(out, format="PNG", optimize=True)
        return out.getvalue(), f"{stem}.png", "image/png"
    im.convert("RGB").save(out, format="JPEG", quality=q, optimize=True)
    return out.getvalue(), f"{stem}.jpg", "image/jpeg"


def _maybe_downscale_sticker_bytes(data: bytes, filename: str, mime: str) -> tuple[bytes, str, str]:
    """
    缩小表情包并可选中心画布留白（见 TELEGRAM_STICKER_CANVAS_EDGE）。
    GIF 不动（避免拆帧）。TELEGRAM_STICKER_MAX_EDGE=0 则跳过。
    """
    max_edge = int(TELEGRAM_STICKER_MAX_EDGE or 0)
    max_bytes = int(TELEGRAM_STICKER_MAX_BYTES_BEFORE_RECOMPRESS or 380_000)
    canvas_edge = int(TELEGRAM_STICKER_CANVAS_EDGE or 0)
    if max_edge <= 0 or not data:
        return data, filename, mime
    try:
        from PIL import Image
    except ImportError:
        logger.warning("表情包缩放需 Pillow（pip install Pillow），当前原图发送，聊天里仍会很大")
        return data, filename, mime

    ext = Path(filename or "").suffix.lower()
    if ext == ".gif":
        logger.debug("表情包 GIF 未缩放，如需变小请改用静图或后续再加拆帧")
        return data, filename, mime

    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception as e:
        logger.debug("表情包 PIL 无法打开，原样发送: %s", e)
        return data, filename, mime

    w, h = im.size
    if w <= 0 or h <= 0:
        return data, filename, mime

    stem = Path(filename or "sticker").stem or "sticker"
    base_q = min(95, max(50, int(TELEGRAM_STICKER_JPEG_QUALITY or 72)))

    # 长边超过上限：先缩小
    if max(w, h) > max_edge:
        try:
            im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        except Exception as e:
            logger.debug("表情包 thumbnail 失败，原样发送: %s", e)
            return data, filename, mime
    elif len(data) <= max_bytes and canvas_edge <= 0:
        # 无画布模式：尺寸与体积都可接受则不再编码
        return data, filename, mime

    # 中心画布：透明边距，主体在画面中间
    if canvas_edge > 0:
        try:
            im = _letterbox_sticker_on_canvas(im, canvas_edge)
        except Exception as e:
            logger.warning("表情包画布合成失败，按无画布发送: %s", e)

    # 输出字节
    try:
        out_b, out_name, out_mime = _sticker_pil_to_send_bytes(im, stem, base_q)
        if len(out_b) > int(max_bytes * 1.15) and out_mime == "image/jpeg":
            q2 = max(50, base_q - 18)
            out_b2, out_name2, out_mime2 = _sticker_pil_to_send_bytes(im, stem, q2)
            if len(out_b2) < len(out_b):
                return out_b2, out_name2, out_mime2
        return out_b, out_name, out_mime
    except Exception as e:
        logger.debug("表情包重编码失败，原样发送: %s", e)
        return data, filename, mime


def send_sticker_photo(chat_id: int, r2_key: str, bot_token: Optional[str] = None) -> bool:
    """
    发送表情包：拉取原图（公网 URL 或桶内字节），可选缩小后 multipart 发 sendPhoto。
    """
    tok = _effective_tg_token(bot_token)
    if not tok or not r2_key:
        return False
    url_api = f"{TELEGRAM_API_BASE}{tok}/sendPhoto"
    data: Optional[bytes] = None
    ctype: str = ""

    base = (R2_PUBLIC_URL or "").strip().rstrip("/")
    if base:
        photo_url = f"{base}/{str(r2_key).lstrip('/')}"
        try:
            r = requests.get(photo_url, timeout=45)
            if r.status_code == 200 and r.content:
                data = r.content
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        except requests.RequestException as e:
            logger.warning("表情包拉取公网图失败 key=%s: %s", r2_key, e)

    if not data:
        data, ctype = r2_store.get_object_bytes(r2_key)
    if not data:
        logger.warning("表情包无数据 key=%s", r2_key)
        return False

    name = str(r2_key).split("/")[-1] or "sticker.jpg"
    mime = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
    data, name, mime = _maybe_downscale_sticker_bytes(data, name, mime)

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

    with _CTX_LOCK:
        history = list(_CONTEXT_MESSAGES.get(user_id) or [])
        if not history:
            history = _bootstrap_context_from_r2(window_id)
            if history:
                _CONTEXT_MESSAGES[user_id] = list(history)
    history = _trim_context_messages(history)
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
        reply_text = _sanitize_reply_for_telegram(reply_text)
        # 电脑控制标签：入队并从可见正文移除（与手机/Tasker 隔离）
        reply_text, _ = process_pcmd_in_assistant_text(reply_text)
        # 写入上下文时不带 <voice> 与 [情绪标签]，避免污染多轮记忆
        for_ctx = reply_text
        for_ctx, _ = _extract_voice_tag(for_ctx)
        for_ctx, _ = _extract_sticker_tag(for_ctx)
        # 更新上下文：只缓存 user/assistant（不存 system），下次请求自动带上
        with _CTX_LOCK:
            cur = list(_CONTEXT_MESSAGES.get(user_id) or [])
            cur.append({"role": "user", "content": merged_user_content})
            cur.append({"role": "assistant", "content": for_ctx})
            _CONTEXT_MESSAGES[user_id] = _trim_context_messages(cur)
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


def _set_my_commands_wenyou_group(cmd_token: str) -> bool:
    """文游固定群：/story /go /end /settle（仅在该群菜单中显示）；cmd_token 为承担文游菜单的 Bot。"""
    if not WENYOU_GROUP_CHAT_ID:
        return False
    tok = (cmd_token or "").strip()
    if not tok:
        return False
    url = f"{TELEGRAM_API_BASE}{tok}/setMyCommands"
    payload = {
        "commands": [
            {"command": "story", "description": "开局（随机或加关键词）"},
            {"command": "go", "description": "结算本轮，推进剧情"},
            {"command": "end", "description": "结束副本并进入系统空间结算"},
            {"command": "settle", "description": "完成最终结算并归档本局"},
        ],
        "scope": {"type": "chat", "chat_id": int(WENYOU_GROUP_CHAT_ID)},
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            logger.warning("setMyCommands(wenyou) 非 200 status=%s body=%s", r.status_code, (r.text or "")[:200])
            return False
        data = r.json() if r.content else {}
        return bool(data.get("ok", True))
    except Exception as e:
        logger.warning("setMyCommands(wenyou) 失败: %s", e)
        return False


## 已移除：按钮式 Todo 便签（避免占用输入区交互与 R2 写入）


def send_message(
    chat_id: int,
    text: str,
    bot_token: Optional[str] = None,
    reply_markup: Optional[dict] = None,
) -> bool:
    """向指定 chat 发送一条文字消息。HTTP 200 时也检查 body 里 ok，避免 Telegram 返回 200 但未送达（如被拉黑）。"""
    tok = _effective_tg_token(bot_token)
    if not tok:
        return False
    url = f"{TELEGRAM_API_BASE}{tok}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
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


def send_message_to_user(telegram_user_id: int, text: str, bot_token: Optional[str] = None) -> bool:
    """
    向指定 Telegram 用户发消息（用于主动发消息等）。
    chat_id 与 user 私聊时等于 telegram_user_id。
    """
    return send_message(chat_id=telegram_user_id, text=text, bot_token=bot_token)


def send_message_segmented(chat_id: int, text: str, bot_token: Optional[str] = None) -> bool:
    """把一段长文本拆成多条发回 Telegram（带间隔）。"""
    parts = _split_reply_text(text)
    if not parts:
        return send_message(chat_id=chat_id, text=text or "", bot_token=bot_token)
    ok_any = False
    for i, part in enumerate(parts):
        ok = send_message(chat_id=chat_id, text=part, bot_token=bot_token)
        ok_any = ok_any or ok
        # 最后一条不 sleep
        if i != len(parts) - 1:
            _sleep_between_sends()
    return ok_any


def _split_reply_text_by_len_only(text: str) -> list[str]:
    """
    仅按长度硬切分，不按换行/段落切。
    用于 GM 回复：保留原始换行展示，避免“每行一条”。
    """
    t = (text or "").strip()
    if not t:
        return []
    max_len = int(TELEGRAM_OUTPUT_CHUNK_CHARS or 1500)
    max_len = max(200, min(4096, max_len))
    out: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        out.append(t[i : i + max_len])
        i += max_len
    return out


def send_message_segmented_gm(chat_id: int, text: str, bot_token: Optional[str] = None) -> bool:
    """GM 专用发送：仅长度切分，保留换行，不按行拆条。"""
    parts = _split_reply_text_by_len_only(text)
    if not parts:
        return send_message(chat_id=chat_id, text=text or "", bot_token=bot_token)
    ok_any = False
    for i, part in enumerate(parts):
        ok = send_message(chat_id=chat_id, text=part, bot_token=bot_token)
        ok_any = ok_any or ok
        if i != len(parts) - 1:
            _sleep_between_sends()
    return ok_any


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
        reply = "暂时没连上渡，稍后再试哦～"
    # 解析语音标签
    reply_clean, voice_text = _extract_voice_tag(reply)
    reply_clean = _sanitize_reply_for_telegram(reply_clean)
    # 表情包：[tag] 拆出后先发正文再发图
    reply_clean, sticker_tag = _extract_sticker_tag(reply_clean)

    # 先发文字（短信分段）
    ok_text = send_message_segmented(chat_id=chat_id, text=reply_clean, bot_token=bot_token) if reply_clean else True

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
    """在服务启动时调用：清主 Bot 默认命令菜单、设文游群专属命令等。Webhook 模式下无需轮询。"""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN 未配置，Telegram 功能将不可用")
        return
    _delete_my_commands_default()
    if WENYOU_GROUP_CHAT_ID:
        # 文游菜单挂在主 Bot 或专用 GM Bot（若配置了 TELEGRAM_GM_BOT_TOKEN）
        wtok = TELEGRAM_GM_BOT_TOKEN or TELEGRAM_BOT_TOKEN
        _set_my_commands_wenyou_group(wtok)


def handle_telegram_update(upd: dict, bot_token: Optional[str] = None):
    """
    处理一条 Telegram update。
    - 主 Bot：POST /telegram/webhook，bot_token=TELEGRAM_BOT_TOKEN（私聊渡、运维 /start）。
    - 文游 GM Bot（可选）：POST /telegram/webhook_gm，bot_token=TELEGRAM_GM_BOT_TOKEN（仅文游群）。
    若未配置 TELEGRAM_GM_BOT_TOKEN，行为与旧版一致：文游仍在主 Bot 上处理。
    """
    token = _effective_tg_token(bot_token)
    if not token:
        return
    gm_split = bool(TELEGRAM_GM_BOT_TOKEN)
    is_gm = gm_split and token == TELEGRAM_GM_BOT_TOKEN
    is_main = token == TELEGRAM_BOT_TOKEN
    if gm_split and not is_gm and not is_main:
        return

    msg = (upd or {}).get("message") or (upd or {}).get("edited_message")
    if not msg:
        return
    chat_id = msg.get("chat", {}).get("id")
    chat_type = (msg.get("chat") or {}).get("type") or ""
    from_user = msg.get("from") or {}
    user_id = from_user.get("id")
    if chat_id is None or user_id is None:
        return

    text = (msg.get("text") or "").strip()
    caption = (msg.get("caption") or "").strip()

    # —— 文游专用 GM Bot：只处理文游群；其它聊天仅简短提示 ——
    if is_gm:
        if (not text) and msg.get("photo"):
            return
        if not text:
            return
        if not WENYOU_GROUP_CHAT_ID or int(chat_id) != int(WENYOU_GROUP_CHAT_ID):
            if chat_type == "private":
                send_message(
                    int(chat_id),
                    "本 Bot 仅用于文游跑团群。与渡私聊请使用主 Bot。",
                    bot_token=token,
                )
            return
        parts = text.strip().split(maxsplit=1)
        cmd0 = (parts[0] if parts else "").split("@", 1)[0].lower()
        if cmd0 == "/start":
            send_message(
                int(chat_id),
                "MiniApp 与运维面板请在私聊对主 Bot 发送 /start。本群文游：/story /go /end /settle。",
                bot_token=token,
            )
            return
        if cmd0 == "/story":
            rest = parts[1] if len(parts) > 1 else None
            out = cmd_story(int(chat_id), rest)
            send_message_segmented_gm(int(chat_id), out, bot_token=token)
            return
        if cmd0 == "/go":
            out = cmd_go(int(chat_id))
            send_message_segmented_gm(int(chat_id), out, bot_token=token)
            return
        if cmd0 == "/end":
            out = cmd_end(int(chat_id))
            send_message(int(chat_id), out, bot_token=token)
            return
        if cmd0 == "/settle":
            out = cmd_settle(int(chat_id))
            send_message(int(chat_id), out, bot_token=token)
            return
        # 群内普通发言也记入文游玩家行动，供后续 /go 让 GM 基于行动推进剧情。
        record_group_player_line(int(chat_id), text)
        return

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
        return

    # 文游群内：主 Bot 发的消息 = 玩家二（渡）发言，记入本轮（仅你发 /story /go /end 等指令）
    if (
        token == TELEGRAM_BOT_TOKEN
        and WENYOU_GROUP_CHAT_ID
        and int(chat_id) == int(WENYOU_GROUP_CHAT_ID)
        and not text.startswith("/")
        and _is_message_from_main_bot(msg)
    ):
        record_group_player2_line(text, session_id=int(chat_id))
        return

    # 已配置 GM Bot 时：
    # - /story /go /end 等文游指令由 GM Webhook 处理
    # - 群内普通发言仍由主 Bot 按“私聊同逻辑”走网关回复（玩家二发言）
    #   同时 GM Bot 已在其 webhook 侧记录玩家行动，这里不再重复 record。
    if gm_split and WENYOU_GROUP_CHAT_ID and int(chat_id) == int(WENYOU_GROUP_CHAT_ID):
        if text.startswith("/"):
            return
        # 走主链路（聚合输入 -> 调网关 -> 主 Bot 回复）
        append_user_input(chat_id=int(chat_id), user_id=int(user_id), text=text)
        return

    # 未配置 GM Bot 时：文游仍在主 Bot 上（与旧版一致）
    if not gm_split and WENYOU_GROUP_CHAT_ID and int(chat_id) == int(WENYOU_GROUP_CHAT_ID):
        parts = text.strip().split(maxsplit=1)
        cmd0 = (parts[0] if parts else "").split("@", 1)[0].lower()
        if cmd0 == "/start":
            send_message(
                int(chat_id),
                "MiniApp 与运维面板请在私聊对 Bot 发送 /start。本群文游：/story /go /end /settle（主神积分、系统商店、等级阶位 D～S、血统与体力/智慧见剧情与状态栏）。",
                bot_token=token,
            )
            return
        if cmd0 == "/story":
            rest = parts[1] if len(parts) > 1 else None
            out = cmd_story(int(chat_id), rest)
            send_message_segmented(int(chat_id), out, bot_token=token)
            return
        if cmd0 == "/go":
            out = cmd_go(int(chat_id))
            send_message_segmented(int(chat_id), out, bot_token=token)
            return
        if cmd0 == "/end":
            out = cmd_end(int(chat_id))
            send_message(int(chat_id), out, bot_token=token)
            return
        if cmd0 == "/settle":
            out = cmd_settle(int(chat_id))
            send_message(int(chat_id), out, bot_token=token)
            return
        record_group_player_line(int(chat_id), text)
        return

    # /start：仅收个口，不弹 Reply 键盘（MiniApp 用 Bot 自带 Menu 入口即可）
    cmd0 = (text.strip().split()[0] if text else "").split("@", 1)[0].lower()
    if cmd0 == "/start":
        send_message(
            int(chat_id),
            "渡已就绪。MiniApp 请用聊天栏旁的 Menu 打开；此处不再弹出第二套键盘或命令菜单。",
            bot_token=token,
            reply_markup={"remove_keyboard": True},
        )
        return

    logger.info("收到 TG 消息 user_id=%s chat_id=%s len=%d", user_id, chat_id, len(text))
    if TELEGRAM_PROACTIVE_TARGET_USER_ID and user_id == TELEGRAM_PROACTIVE_TARGET_USER_ID:
        from utils.time_aware import now_beijing_iso

        r2_store.save_last_telegram_user_activity_at(now_beijing_iso())
    # 文游进行中时，私聊自动给“切回日常聊天”提示，避免渡在私聊继续跑副本剧情。
    final_text = text
    if (
        chat_type == "private"
        and not text.startswith("/")
        and _is_wenyou_active()
        and "[当前在私聊" not in text
    ):
        final_text = (
            "[当前在私聊，不在文游群；此消息按日常聊天处理，不推进副本剧情。]\n"
            + text
        )
    append_user_input(chat_id=chat_id, user_id=user_id, text=final_text)
