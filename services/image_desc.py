# 便宜图像 AI：将图片转为文字描述，用于存 R2（与转发给 Claude 的原图并行）
import base64
import copy
import hashlib
import io
import math
import re
import threading
import time
import uuid
from typing import Optional

import requests

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

from config import IMAGE_DESC_API_URL, IMAGE_DESC_API_KEY, IMAGE_DESC_MODEL
from utils.log import get_logger


ANTHROPIC_IMAGE_MAX_LONG_EDGE = 1568
ANTHROPIC_IMAGE_MAX_PIXELS = 1_150_000
_RESIZABLE_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_IMAGE_PLACEHOLDER_RE = re.compile(r"\[\[DU_IMAGE_DESC:(img_[0-9a-f]{16})\]\]")
_DESC_CACHE: dict[str, str] = {}
_DESC_PENDING: dict[str, threading.Event] = {}
_DESC_LOCK = threading.Lock()
logger = get_logger(__name__)


def image_to_description(image_base64: str, mime_type: str = "image/jpeg") -> Optional[str]:
    """
    调用配置的图像描述 API，返回文字描述。
    若未配置 API 或调用失败，返回 None（不阻塞主流程）。
    """
    if not IMAGE_DESC_API_URL or not IMAGE_DESC_API_KEY:
        logger.info("image_desc 跳过：未配置 IMAGE_DESC_API_URL/API_KEY")
        return None
    # 通用格式：带 data URL 的 messages，与 OpenAI 格式兼容
    url = IMAGE_DESC_API_URL.strip().rstrip("/")
    if "/chat/completions" not in url:
        url = url + "/v1/chat/completions" if "/v1" not in url else url + "/chat/completions"
    headers = {"Authorization": f"Bearer {IMAGE_DESC_API_KEY}", "Content-Type": "application/json"}
    # 根据 data URL 解析
    if image_base64.startswith("data:"):
        # data:image/jpeg;base64,xxxx
        parts = image_base64.split(",", 1)
        if len(parts) == 2:
            image_base64 = parts[1]
    payload = {
        "model": IMAGE_DESC_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "用一两句话描述这张图片的内容，用于存档检索。"},
                    {
                        "type": "text",
                        "text": (
                            "如果这是表情包、贴纸、梗图或聊天截图，要明确写出“表情包/贴纸/梗图/聊天截图”，"
                            "并概括画面文字、人物动作和表达的情绪。不要编造看不见的细节。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                    },
                ],
            }
        ],
        "max_tokens": 200,
    }
    started = time.perf_counter()
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        desc = content.strip() if content else ""
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "image_desc 调用完成 model=%s mime=%s elapsed_ms=%s desc_len=%s",
            IMAGE_DESC_MODEL,
            mime_type,
            elapsed_ms,
            len(desc),
        )
        return desc or None
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.warning(
            "image_desc 调用失败 model=%s mime=%s elapsed_ms=%s status=%s error=%s",
            IMAGE_DESC_MODEL,
            mime_type,
            elapsed_ms,
            status,
            e,
        )
        return None


def extract_images_from_messages(messages: list) -> list:
    """
    从 messages 中抽出所有图片（content 中的 image_url 或 base64）。
    返回 [ (message_index, content_item_index, base64, mime_type), ... ]
    """
    out = []
    for mi, msg in enumerate(messages):
        content = msg.get("content")
        if isinstance(content, str):
            continue
        if not isinstance(content, list):
            continue
        for ci, item in enumerate(content):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "image_url":
                url = (item.get("image_url") or {}).get("url", "")
                if url.startswith("data:"):
                    # data:image/png;base64,xxx
                    parts = url.split(",", 1)
                    if len(parts) == 2:
                        mt = "image/png"
                        if ";" in parts[0]:
                            mt = parts[0].split(";")[0].replace("data:", "")
                        out.append((mi, ci, parts[1], mt))
            elif item.get("type") == "image" and "image_url" in item:
                # 部分 API 用 image 里嵌 image_url
                url = item.get("image_url", {}).get("url", "")
                if url.startswith("data:"):
                    parts = url.split(",", 1)
                    if len(parts) == 2:
                        mt = "image/png"
                        if ";" in parts[0]:
                            mt = parts[0].split(";")[0].replace("data:", "")
                        out.append((mi, ci, parts[1], mt))
    return out


def _split_data_url(url: str) -> tuple[str, str] | None:
    raw = str(url or "").strip()
    if not raw.startswith("data:") or "," not in raw:
        return None
    head, payload = raw.split(",", 1)
    if ";base64" not in head:
        return None
    mime_type = "image/png"
    if ";" in head:
        mime_type = head.split(";", 1)[0].replace("data:", "").strip().lower() or mime_type
    return mime_type, payload


def image_description_key(image_base64: str, mime_type: str = "image/jpeg") -> str:
    payload = str(image_base64 or "")
    if payload.startswith("data:"):
        parsed = _split_data_url(payload)
        if parsed:
            mime_type, payload = parsed
    mt = str(mime_type or "image/jpeg").strip().lower()
    return f"{mt}:{hashlib.sha256(payload.encode('utf-8', errors='ignore')).hexdigest()}"


def image_description_id(image_base64: str, mime_type: str = "image/jpeg") -> str:
    key = image_description_key(image_base64, mime_type)
    digest = key.rsplit(":", 1)[-1]
    return f"img_{digest[:16]}"


def image_placeholder_text(image_id: str) -> str:
    ident = str(image_id or "").strip()
    return f"[[DU_IMAGE_DESC:{ident}]]" if ident else "[图片]"


def mark_image_description_pending(image_base64: str, mime_type: str = "image/jpeg") -> str:
    key = image_description_key(image_base64, mime_type)
    with _DESC_LOCK:
        if key not in _DESC_CACHE and key not in _DESC_PENDING:
            _DESC_PENDING[key] = threading.Event()
    return key


def finish_image_description(image_base64: str, mime_type: str, description: Optional[str]) -> None:
    key = image_description_key(image_base64, mime_type)
    desc = str(description or "").strip()
    with _DESC_LOCK:
        if desc:
            _DESC_CACHE[key] = desc
        event = _DESC_PENDING.pop(key, None)
    if event:
        event.set()


def get_cached_image_description(image_base64: str, mime_type: str, wait_seconds: float = 0.0) -> Optional[str]:
    key = image_description_key(image_base64, mime_type)
    with _DESC_LOCK:
        desc = _DESC_CACHE.get(key)
        event = _DESC_PENDING.get(key)
    if desc:
        return desc
    if event and wait_seconds > 0:
        event.wait(wait_seconds)
        with _DESC_LOCK:
            return _DESC_CACHE.get(key)
    return None


def has_pending_image_description(image_base64: str, mime_type: str = "image/jpeg") -> bool:
    key = image_description_key(image_base64, mime_type)
    with _DESC_LOCK:
        return key in _DESC_PENDING


def extract_image_payload_from_part(part: dict) -> tuple[str, str] | None:
    if not isinstance(part, dict):
        return None
    image_url = None
    if part.get("type") == "image_url":
        image_url = part.get("image_url") if isinstance(part.get("image_url"), dict) else None
    elif part.get("type") == "image" and isinstance(part.get("image_url"), dict):
        image_url = part.get("image_url")
    if not image_url:
        return None
    parsed = _split_data_url(image_url.get("url") or "")
    if not parsed:
        return None
    mime_type, payload = parsed
    return payload, mime_type


def image_part_archive_description(part: dict, wait_seconds: float = 3.0) -> Optional[str]:
    parsed = extract_image_payload_from_part(part)
    if not parsed:
        return None
    payload, mime_type = parsed
    was_pending = has_pending_image_description(payload, mime_type)
    desc = get_cached_image_description(payload, mime_type, wait_seconds=wait_seconds)
    if desc:
        return desc
    if was_pending:
        return None
    desc = image_to_description(payload, mime_type)
    finish_image_description(payload, mime_type, desc)
    return desc


def image_part_archive_text(part: dict) -> str:
    parsed = extract_image_payload_from_part(part)
    if not parsed:
        return "[图片]"
    payload, mime_type = parsed
    desc = get_cached_image_description(payload, mime_type, wait_seconds=0.0)
    if desc:
        return f"[图片：{desc}]"
    return image_placeholder_text(image_description_id(payload, mime_type))


def replace_image_placeholders_in_text(text: str, desc_map: dict[str, str] | None) -> str:
    if not text or not isinstance(text, str):
        return text
    mapping = desc_map or {}

    def _repl(match: re.Match) -> str:
        image_id = match.group(1)
        desc = str(mapping.get(image_id) or "").strip()
        return f"[图片：{desc}]" if desc else "[图片]"

    return _IMAGE_PLACEHOLDER_RE.sub(_repl, text)


def replace_image_placeholders_in_obj(obj, desc_map: dict[str, str] | None):
    if isinstance(obj, str):
        return replace_image_placeholders_in_text(obj, desc_map)
    if isinstance(obj, list):
        return [replace_image_placeholders_in_obj(item, desc_map) for item in obj]
    if isinstance(obj, dict):
        return {k: replace_image_placeholders_in_obj(v, desc_map) for k, v in obj.items()}
    return obj


def _encode_resized_image(img) -> tuple[str, str]:
    out = io.BytesIO()
    if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
        img = bg
    else:
        img = img.convert("RGB")
    img.save(out, format="JPEG", quality=86, optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii"), "image/jpeg"


def compress_base64_image_for_anthropic(image_base64: str, mime_type: str) -> tuple[str, str, dict]:
    """
    按 Anthropic vision 建议压缩：长边 <= 1568px，且总像素 <= 1.15MP。
    只处理 JPEG/PNG/WebP；GIF 等动图保持原样，避免破坏语义。
    返回 (base64, mime_type, meta)。
    """
    mt = str(mime_type or "image/png").strip().lower()
    if mt == "image/jpg":
        mt = "image/jpeg"
    if mt not in _RESIZABLE_MIME_TYPES:
        return image_base64, mime_type, {"changed": False, "reason": "unsupported_mime", "mime_type": mt}
    if Image is None or ImageOps is None:
        return image_base64, mime_type, {"changed": False, "reason": "pillow_missing", "mime_type": mt}
    try:
        raw = base64.b64decode(str(image_base64 or ""), validate=False)
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        if width <= 0 or height <= 0:
            return image_base64, mime_type, {"changed": False, "reason": "invalid_size", "mime_type": mt}
        long_edge = max(width, height)
        pixels = width * height
        scale = min(
            1.0,
            ANTHROPIC_IMAGE_MAX_LONG_EDGE / float(long_edge),
            math.sqrt(ANTHROPIC_IMAGE_MAX_PIXELS / float(pixels)),
        )
        if scale >= 0.999:
            return image_base64, mime_type, {
                "changed": False,
                "reason": "already_within_limit",
                "mime_type": mt,
                "width": width,
                "height": height,
            }
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        resample = getattr(Image, "Resampling", Image).LANCZOS
        img = img.resize(new_size, resample)
        out_b64, out_mime = _encode_resized_image(img)
        return out_b64, out_mime, {
            "changed": True,
            "mime_type": mt,
            "output_mime_type": out_mime,
            "width": width,
            "height": height,
            "new_width": new_size[0],
            "new_height": new_size[1],
            "bytes": len(raw),
            "new_bytes": len(base64.b64decode(out_b64, validate=False)),
        }
    except Exception as e:
        return image_base64, mime_type, {"changed": False, "reason": "resize_failed", "error": str(e)[:160], "mime_type": mt}


def compress_images_for_anthropic(body: dict) -> tuple[dict, list[dict]]:
    """
    压缩 OpenAI 兼容 messages 里的 base64 图片，降低 Claude vision token。
    远程 image_url 不动。
    """
    messages = (body or {}).get("messages") or []
    if not isinstance(messages, list):
        return body, []
    out_body = None
    stats: list[dict] = []
    for mi, msg in enumerate(messages):
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for ci, item in enumerate(content):
            if not isinstance(item, dict):
                continue
            image_url = item.get("image_url") if isinstance(item.get("image_url"), dict) else None
            if not image_url:
                continue
            parsed = _split_data_url(image_url.get("url") or "")
            if not parsed:
                continue
            mime_type, payload = parsed
            new_b64, new_mime, meta = compress_base64_image_for_anthropic(payload, mime_type)
            meta.update({"message_index": mi, "content_index": ci})
            stats.append(meta)
            if not meta.get("changed"):
                continue
            if out_body is None:
                out_body = copy.deepcopy(body)
            out_item = out_body["messages"][mi]["content"][ci]
            out_item["image_url"]["url"] = f"data:{new_mime};base64,{new_b64}"
    return (out_body or body), stats
