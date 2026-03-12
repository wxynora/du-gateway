# 便宜图像 AI：将图片转为文字描述，用于存 R2（与转发给 Claude 的原图并行）
import base64
import uuid
from typing import Optional

import requests

from config import IMAGE_DESC_API_URL, IMAGE_DESC_API_KEY, IMAGE_DESC_MODEL


def image_to_description(image_base64: str, mime_type: str = "image/jpeg") -> Optional[str]:
    """
    调用配置的图像描述 API，返回文字描述。
    若未配置 API 或调用失败，返回 None（不阻塞主流程）。
    """
    if not IMAGE_DESC_API_URL or not IMAGE_DESC_API_KEY:
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
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                    },
                ],
            }
        ],
        "max_tokens": 200,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        return content.strip() if content else None
    except Exception:
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
