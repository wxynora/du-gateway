import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import DATA_DIR, TARGET_AI_URL, TARGET_AI_API_KEY, TARGET_AI_URLS, TARGET_AI_API_KEYS
from config import (
    OPENROUTER_FIXED_MODEL,
    SILICONFLOW_BASE_HOST,
    SILICONFLOW_DEFAULT_MODEL,
    is_openrouter_url,
)


UPSTREAMS_FILE = DATA_DIR / "upstreams.json"
ACTIVE_MODEL_FILE = DATA_DIR / "active_upstream_model.json"
CLAUDE_THINKING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_CLAUDE_THINKING_EFFORT = "high"


def _default_payload():
    """
    默认从环境变量构建上游列表：
    - TARGET_AI_URL (+ TARGET_AI_API_KEY)
    - TARGET_AI_URLS (+ TARGET_AI_API_KEYS)
    """
    items = []
    seen = set()
    if TARGET_AI_URL and TARGET_AI_URL.strip():
        u = TARGET_AI_URL.strip()
        if u not in seen:
            items.append({"name": "default", "url": u, "api_key": TARGET_AI_API_KEY or ""})
            seen.add(u)
    if TARGET_AI_URLS:
        keys = list(TARGET_AI_API_KEYS or [])
        while len(keys) < len(TARGET_AI_URLS):
            keys.append(TARGET_AI_API_KEY or "")
        for i, (u, k) in enumerate(zip(TARGET_AI_URLS, keys[: len(TARGET_AI_URLS)])):
            u = (u or "").strip()
            if not u or u in seen:
                continue
            items.append({"name": f"upstream{i+1}", "url": u, "api_key": k or ""})
            seen.add(u)
    return {"active": 0, "items": items}


def load_upstreams() -> dict:
    """
    开启“切换”模式时：items 永远来自环境变量（只允许切换 active）。
    files 里仅保存 active，避免手机端任意改 URL 列表。
    """
    payload = _default_payload()
    items = payload.get("items") or []
    if not UPSTREAMS_FILE.exists():
        return {"active": 0, "items": items}
    try:
        with open(UPSTREAMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return {"active": 0, "items": items}

    active = int(data.get("active") or 0)
    if active < 0 or active >= len(items):
        active = 0
    return {"active": active, "items": items}


def save_upstreams(payload: dict) -> bool:
    # 只保存 active，items 从 env 重新构建。
    UPSTREAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(UPSTREAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "active": int(payload.get("active") or 0),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        return True
    except Exception:
        return False


def _chat_url_to_models_url(chat_url: str) -> str:
    base = str(chat_url or "").strip().rstrip("/")
    if not base:
        return ""
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/models"


def _load_active_model_payload() -> dict:
    if not ACTIVE_MODEL_FILE.exists():
        return {}
    try:
        with open(ACTIVE_MODEL_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_active_model_payload(payload: dict) -> bool:
    ACTIVE_MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(ACTIVE_MODEL_FILE, "w", encoding="utf-8") as f:
            json.dump(payload or {}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def normalize_claude_thinking_effort(value: str) -> str:
    effort = str(value or "").strip().lower()
    return effort if effort in CLAUDE_THINKING_EFFORTS else DEFAULT_CLAUDE_THINKING_EFFORT


def _current_active_identity() -> tuple[int, str]:
    data = load_upstreams()
    items = data.get("items") or []
    active = int(data.get("active") or 0)
    if active < 0 or active >= len(items):
        return active, ""
    return active, str((items[active] or {}).get("url") or "").strip()


def get_active_claude_thinking_effort() -> str:
    payload = _load_active_model_payload()
    active, url = _current_active_identity()
    if payload.get("active") == active and str(payload.get("url") or "").strip() == url:
        return normalize_claude_thinking_effort(payload.get("claude_thinking_effort"))
    return DEFAULT_CLAUDE_THINKING_EFFORT


def set_active_claude_thinking_effort(effort: str) -> bool:
    active, url = _current_active_identity()
    if not url:
        return False
    payload = _load_active_model_payload()
    model = ""
    if payload.get("active") == active and str(payload.get("url") or "").strip() == url:
        model = str(payload.get("model") or "").strip()
    return _save_active_model_payload(
        {
            "active": active,
            "url": url,
            "model": model,
            "claude_thinking_effort": normalize_claude_thinking_effort(effort),
            "checked_at": time.time(),
        }
    )


def clear_active_model_cache() -> bool:
    return _save_active_model_payload({})


def _is_siliconflow_url(url: str) -> bool:
    host = (urlparse(str(url or "").strip()).hostname or "").lower()
    return bool(host and SILICONFLOW_BASE_HOST and host.endswith(SILICONFLOW_BASE_HOST))


def list_models_for_item_detail(it: dict) -> dict:
    url = str((it or {}).get("url") or "").strip()
    api_key = str((it or {}).get("api_key") or "").strip()
    if not url:
        return {"ok": False, "models": [], "status": 0, "source": "", "error": "URL 为空"}
    if is_openrouter_url(url):
        model = str(OPENROUTER_FIXED_MODEL or "").strip()
        return {
            "ok": bool(model),
            "models": [model] if model else [],
            "status": 200 if model else 0,
            "source": "openrouter_fixed_model",
            "error": "" if model else "OPENROUTER_FIXED_MODEL 未配置",
        }
    if _is_siliconflow_url(url) and SILICONFLOW_DEFAULT_MODEL:
        return {
            "ok": True,
            "models": [str(SILICONFLOW_DEFAULT_MODEL or "").strip()],
            "status": 200,
            "source": "siliconflow_default_model",
            "error": "",
        }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    models_url = _chat_url_to_models_url(url)
    try:
        resp = requests.get(models_url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return {
                "ok": False,
                "models": [],
                "status": int(resp.status_code or 0),
                "source": "upstream_v1_models",
                "error": (resp.text or "")[:300] or f"HTTP {resp.status_code}",
            }
        data = resp.json() if resp.content else {}
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return {
                "ok": False,
                "models": [],
                "status": int(resp.status_code or 0),
                "source": "upstream_v1_models",
                "error": "上游 /v1/models 未返回 data 列表",
            }
        out = []
        for item in items:
            if isinstance(item, dict) and str(item.get("id") or "").strip():
                out.append(str(item.get("id") or "").strip())
            elif isinstance(item, str) and item.strip():
                out.append(item.strip())
        return {
            "ok": bool(out),
            "models": out,
            "status": int(resp.status_code or 0),
            "source": "upstream_v1_models",
            "error": "" if out else "上游 /v1/models 返回空列表",
        }
    except Exception as e:
        return {
            "ok": False,
            "models": [],
            "status": 0,
            "source": "upstream_v1_models",
            "error": str(e),
        }


def list_models_for_item(it: dict) -> list[str]:
    detail = list_models_for_item_detail(it)
    return list(detail.get("models") or []) if isinstance(detail, dict) else []


def _fetch_first_model_for_item(it: dict) -> str:
    models = list_models_for_item(it)
    return models[0] if models else ""


def refresh_active_model_cache() -> str:
    data = load_upstreams()
    items = data.get("items") or []
    active = int(data.get("active") or 0)
    if active < 0 or active >= len(items):
        _save_active_model_payload({})
        return ""
    item = items[active] or {}
    effort = get_active_claude_thinking_effort()
    model = _fetch_first_model_for_item(item)
    _save_active_model_payload(
        {
            "active": active,
            "url": str(item.get("url") or "").strip(),
            "model": model,
            "claude_thinking_effort": effort,
            "checked_at": time.time(),
        }
    )
    return model


def get_cached_active_model(refresh_if_missing: bool = True) -> str:
    payload = _load_active_model_payload()
    data = load_upstreams()
    items = data.get("items") or []
    active = int(data.get("active") or 0)
    if 0 <= active < len(items):
        url = str((items[active] or {}).get("url") or "").strip()
        if payload.get("active") == active and str(payload.get("url") or "").strip() == url:
            model = str(payload.get("model") or "").strip()
            if model:
                return model
    if refresh_if_missing:
        return refresh_active_model_cache()
    return ""


def set_active_model(model: str) -> bool:
    model = str(model or "").strip()
    if not model:
        return False
    data = load_upstreams()
    items = data.get("items") or []
    active = int(data.get("active") or 0)
    if active < 0 or active >= len(items):
        return False
    item = items[active] or {}
    effort = get_active_claude_thinking_effort()
    return _save_active_model_payload(
        {
            "active": active,
            "url": str(item.get("url") or "").strip(),
            "model": model,
            "claude_thinking_effort": effort,
            "checked_at": time.time(),
        }
    )


def set_active(index: int) -> bool:
    data = load_upstreams()
    items = data.get("items") or []
    if index < 0 or index >= len(items):
        return False
    data["active"] = int(index)
    ok = save_upstreams(data)
    if ok:
        clear_active_model_cache()
    return ok


def get_active_item() -> dict | None:
    data = load_upstreams()
    items = data.get("items") or []
    idx = int(data.get("active") or 0)
    if not items or idx < 0 or idx >= len(items):
        return None
    return items[idx]
