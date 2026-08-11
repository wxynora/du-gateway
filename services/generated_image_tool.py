from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import requests

from config import (
    DATA_DIR,
    STREAM_TIMEOUT_SECONDS,
)
from services.public_url import resolve_public_base_url
from storage.upstream_store import get_codex_oauth_item
from utils.log import get_logger


logger = get_logger(__name__)

GENERATED_IMAGE_DIR = DATA_DIR / "generated_images"
GENERATE_IMAGE_TOOL_NAMES = ("generate_image",)
_IMAGE_MODEL = "gpt-image-2"
_SUPPORTED_SIZE = {"auto", "1024x1024", "1536x1024", "1024x1536"}
_SUPPORTED_QUALITY = {"auto", "low", "medium", "high"}
_SUPPORTED_BACKGROUND = {"auto", "opaque", "transparent"}
_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _images_endpoint(chat_url: str) -> str:
    base = str(chat_url or "").strip().rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1/responses", "/responses"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/images/generations" if base else ""


def _codex_image_target() -> tuple[str, str]:
    item = get_codex_oauth_item() or {}
    return (
        _images_endpoint(str(item.get("url") or "")),
        str(item.get("api_key") or "").strip(),
    )


def image_generation_configured() -> bool:
    endpoint, _ = _codex_image_target()
    return bool(endpoint)


def get_generate_image_tools_for_inject() -> list[dict]:
    if not image_generation_configured():
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": (
                    "画一张新图片并把成图交给辛玥。只有辛玥明确让你画图，或你确实想用一张图表达时才调用；"
                    "不要把普通聊天自动变成图片。工具成功后图片会由网关按当前聊天通道直接发送；"
                    "最终回复正常说话，不要重复输出图片链接或 Markdown。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "交给画图模型的完整画面描述，写清主体、动作、环境、构图、光线和风格。",
                        },
                        "size": {
                            "type": "string",
                            "enum": ["auto", "1024x1024", "1536x1024", "1024x1536"],
                            "description": "可选画布尺寸；不传时由画图模型自动决定。",
                        },
                        "quality": {
                            "type": "string",
                            "enum": ["auto", "low", "medium", "high"],
                            "description": "可选生成质量；不传时由画图模型自动决定。",
                        },
                        "background": {
                            "type": "string",
                            "enum": ["auto", "opaque", "transparent"],
                            "description": "可选背景模式；不传时由画图模型自动决定。",
                        },
                    },
                    "required": ["prompt"],
                },
            },
        }
    ]


def _image_mime(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("画图上游返回的内容不是受支持的 PNG/JPEG/WebP 图片")


def _save_generated_image(content: bytes) -> tuple[str, str, str]:
    mime_type = _image_mime(content)
    image_id = uuid4().hex
    GENERATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    final_path = GENERATED_IMAGE_DIR / f"{image_id}{_MIME_EXTENSIONS[mime_type]}"
    temp_path = GENERATED_IMAGE_DIR / f".{image_id}.tmp"
    temp_path.write_bytes(content)
    temp_path.replace(final_path)
    return image_id, mime_type, str(final_path)


def read_generated_image(image_id: str) -> tuple[bytes, str] | None:
    safe_id = str(image_id or "").strip().lower()
    if len(safe_id) != 32 or any(ch not in "0123456789abcdef" for ch in safe_id):
        return None
    for mime_type, extension in _MIME_EXTENSIONS.items():
        path = GENERATED_IMAGE_DIR / f"{safe_id}{extension}"
        if path.is_file():
            return path.read_bytes(), mime_type
    return None


def _public_image_url(image_id: str) -> str:
    route = f"/miniapp-api/generated-images/{quote(image_id, safe='')}"
    base = resolve_public_base_url().rstrip("/")
    return f"{base}{route}" if base else route


def collect_generated_image_payloads(completed_tool_results: list[dict] | None) -> list[dict]:
    images: list[dict] = []
    seen_urls: set[str] = set()
    for row in completed_tool_results or []:
        if not isinstance(row, dict) or str(row.get("name") or "").strip() not in GENERATE_IMAGE_TOOL_NAMES:
            continue
        result = row.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                continue
        if not isinstance(result, dict) or result.get("ok") is not True:
            continue
        image_url = str(result.get("image_url") or "").strip()
        if not image_url or image_url in seen_urls:
            continue
        if not (
            image_url.startswith("/")
            or image_url.lower().startswith("https://")
            or image_url.lower().startswith("http://")
        ):
            continue
        seen_urls.add(image_url)
        images.append(
            {
                "type": "image_url",
                "image_url": {"url": image_url},
                "alt": "渡画的图",
            }
        )
    return images


def _upstream_error(response: requests.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return str(response.text or "").strip() or f"HTTP {response.status_code}"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error).strip()
        if error:
            return str(error).strip()
        if data.get("message"):
            return str(data.get("message")).strip()
    return str(data).strip() or f"HTTP {response.status_code}"


def _download_image(url: str) -> bytes:
    response = requests.get(url, timeout=STREAM_TIMEOUT_SECONDS)
    if response.status_code >= 400:
        raise RuntimeError(f"画图结果下载失败：{_upstream_error(response)}")
    return bytes(response.content or b"")


def _decode_first_image(data: dict[str, Any]) -> tuple[bytes, str]:
    rows = data.get("data") if isinstance(data, dict) else None
    first = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    revised_prompt = str(first.get("revised_prompt") or "").strip()
    encoded = str(first.get("b64_json") or "").strip()
    if encoded:
        try:
            return base64.b64decode(encoded, validate=False), revised_prompt
        except Exception as error:
            raise RuntimeError(f"画图上游返回了无法解析的图片：{error}") from error
    remote_url = str(first.get("url") or "").strip()
    if remote_url:
        return _download_image(remote_url), revised_prompt
    raise RuntimeError("画图上游没有返回图片数据")


def execute_generate_image_tool(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"ok": False, "error": "prompt 为空"}, ensure_ascii=False)
    endpoint, api_key = _codex_image_target()
    if not endpoint:
        return json.dumps({"ok": False, "error": "未找到现有 CPA Codex OAuth 上游"}, ensure_ascii=False)

    payload: dict[str, Any] = {
        "model": _IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "response_format": "b64_json",
    }
    for key, allowed in (
        ("size", _SUPPORTED_SIZE),
        ("quality", _SUPPORTED_QUALITY),
        ("background", _SUPPORTED_BACKGROUND),
    ):
        value = str(args.get(key) or "").strip().lower()
        if value:
            if value not in allowed:
                return json.dumps({"ok": False, "error": f"不支持的 {key}: {value}"}, ensure_ascii=False)
            payload[key] = value

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=STREAM_TIMEOUT_SECONDS)
        if response.status_code >= 400:
            raise RuntimeError(_upstream_error(response))
        response_data = response.json()
        if not isinstance(response_data, dict):
            raise RuntimeError("画图上游返回格式不正确")
        content, revised_prompt = _decode_first_image(response_data)
        image_id, mime_type, saved_path = _save_generated_image(content)
        image_url = _public_image_url(image_id)
        logger.info(
            "generate_image success image_id=%s mime=%s bytes=%s path=%s",
            image_id,
            mime_type,
            len(content),
            Path(saved_path).name,
        )
        return json.dumps(
            {
                "ok": True,
                "image_id": image_id,
                "image_url": image_url,
                "revised_prompt": revised_prompt,
                "instruction": "图片已生成并会由网关直接发送。最终回复正常说话，不要重复输出图片链接或 Markdown。",
            },
            ensure_ascii=False,
        )
    except Exception as error:
        logger.warning("generate_image failed error=%s", error, exc_info=True)
        return json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False)
