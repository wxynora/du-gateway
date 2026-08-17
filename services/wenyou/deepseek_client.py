import json
import threading
from pathlib import Path
from typing import Optional

import requests

from config import BASE_DIR
from services.worker_models import get_worker_model
from utils.log import get_logger


logger = get_logger(__name__)

_TEMPLATES_CACHE: Optional[dict] = None
_TEMPLATES_LOCK = threading.Lock()


def _load_templates() -> dict:
    global _TEMPLATES_CACHE
    with _TEMPLATES_LOCK:
        if _TEMPLATES_CACHE is not None:
            return _TEMPLATES_CACHE
        path = Path(BASE_DIR) / "prompts" / "wenyou_templates.json"
        try:
            if path.exists():
                _TEMPLATES_CACHE = json.loads(path.read_text(encoding="utf-8"))
            else:
                _TEMPLATES_CACHE = {"worlds": [], "conflicts": [], "roles": []}
        except Exception:
            logger.exception("读取 wenyou_templates.json 失败")
            _TEMPLATES_CACHE = {"worlds": [], "conflicts": [], "roles": []}
        return _TEMPLATES_CACHE


def call_wenyou_deepseek(
    messages: list[dict],
    system: str,
    temperature: float = 0.7,
    timeout_seconds: int = 120,
) -> Optional[str]:
    """调用 DeepSeek Chat Completions（非流式）。"""
    worker = get_worker_model("background_reasoning")
    if not worker.api_key or not worker.api_url or not worker.model:
        logger.warning("background_reasoning 未配置完整，无法调用文游 GM")
        return None
    body = {
        "model": worker.model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": 8192,
    }
    try:
        r = requests.post(
            worker.api_url,
            headers={"Authorization": f"Bearer {worker.api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=max(10, int(timeout_seconds or 120)),
        )
        if r.status_code != 200:
            logger.warning("文游 DeepSeek 非 200 status=%s body=%s", r.status_code, (r.text or "")[:400])
            return None
        data = r.json() if r.content else {}
        ch0 = (data.get("choices") or [{}])[0] or {}
        msg = ch0.get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        return content.strip() if isinstance(content, str) else str(content).strip()
    except Exception as e:
        logger.exception("文游 DeepSeek 请求失败: %s", e)
        return None
