import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import DATA_DIR, TARGET_AI_URL, TARGET_AI_API_KEY, TARGET_AI_URLS, TARGET_AI_API_KEYS
from config import (
    is_siliconflow_url,
    is_openrouter_url,
    is_pioneer_url,
    is_cloudflare_anthropic_url,
    cloudflare_claude_model_options,
    openrouter_model_options,
    siliconflow_model_options,
)


UPSTREAMS_FILE = DATA_DIR / "upstreams.json"
ACTIVE_MODEL_FILE = DATA_DIR / "active_upstream_model.json"
CLAUDE_THINKING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_CLAUDE_THINKING_EFFORT = "high"
PIONEER_CLAUDE_MODEL_ORDER = (
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-4-1",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
)


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


def _is_claude_proxy_model_id(model: str) -> bool:
    value = str(model or "").strip().lower()
    return value.startswith("claude-")


def pioneer_claude_model_options(models: list[str]) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for model in models or []:
        model = str(model or "").strip()
        if not model or not _is_claude_proxy_model_id(model):
            continue
        key = model.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(model)
    if not candidates:
        return []
    by_key = {m.lower(): m for m in candidates}
    out = [by_key[key] for key in PIONEER_CLAUDE_MODEL_ORDER if key in by_key]
    ordered = {m.lower() for m in out}
    out.extend(m for m in candidates if m.lower() not in ordered)
    return out


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


def _normalize_url_for_key(raw_url: str) -> str:
    url = str(raw_url or "").strip().rstrip("/")
    if not url:
        return ""
    return url.lower()


def _parse_url(raw_url: str):
    url = str(raw_url or "").strip()
    if not url:
        return None
    if "://" not in url:
        url = "http://" + url
    try:
        return urlparse(url)
    except Exception:
        return None


def _upstream_stable_key(item: dict, index: int | None = None) -> str:
    item = item or {}
    explicit = str(item.get("id") or "").strip()
    if explicit:
        return f"id:{explicit}"
    url = str(item.get("url") or "").strip()
    parsed = _parse_url(url)
    host = ((parsed.hostname if parsed else "") or "").lower()
    port = parsed.port if parsed else None
    if host in {"127.0.0.1", "localhost", "::1"}:
        if port == 8317:
            return "local-oauth:codex"
        if port == 8082:
            return "local-oauth:claude"
    normalized_url = _normalize_url_for_key(url)
    if normalized_url:
        return f"url:{normalized_url}"
    name = str(item.get("name") or "").strip().lower()
    if name:
        return f"name:{name}"
    return f"index:{index}" if index is not None else ""


def _current_active_context() -> tuple[int, dict, str, str]:
    data = load_upstreams()
    items = data.get("items") or []
    active = int(data.get("active") or 0)
    if active < 0 or active >= len(items):
        return active, {}, "", ""
    item = items[active] or {}
    url = str(item.get("url") or "").strip()
    return active, item, url, _upstream_stable_key(item, active)


def _active_model_entry_from_payload(payload: dict, active: int, item: dict, url: str, key: str) -> dict:
    if not isinstance(payload, dict):
        return {}
    models_by_upstream = payload.get("models_by_upstream")
    if isinstance(models_by_upstream, dict) and key:
        entry = models_by_upstream.get(key)
        if isinstance(entry, dict):
            return entry
    if str(payload.get("upstream_key") or "").strip() == key and key:
        return payload
    if payload.get("active") == active and str(payload.get("url") or "").strip() == url:
        return payload
    return {}


def get_active_claude_thinking_effort() -> str:
    payload = _load_active_model_payload()
    active, item, url, key = _current_active_context()
    entry = _active_model_entry_from_payload(payload, active, item, url, key)
    if entry:
        return normalize_claude_thinking_effort(entry.get("claude_thinking_effort"))
    return DEFAULT_CLAUDE_THINKING_EFFORT


def set_active_claude_thinking_effort(effort: str) -> bool:
    active, item, url, key = _current_active_context()
    if not url:
        return False
    payload = _load_active_model_payload()
    models_by_upstream = dict(payload.get("models_by_upstream") or {}) if isinstance(payload.get("models_by_upstream"), dict) else {}
    entry = dict(_active_model_entry_from_payload(payload, active, item, url, key) or {})
    entry.update(
        {
            "active": active,
            "url": url,
            "upstream_key": key,
            "model": str(entry.get("model") or "").strip(),
            "claude_thinking_effort": normalize_claude_thinking_effort(effort),
            "checked_at": time.time(),
        }
    )
    if key:
        models_by_upstream[key] = entry
    return _save_active_model_payload(
        {
            "active": active,
            "url": url,
            "upstream_key": key,
            "model": str(entry.get("model") or "").strip(),
            "claude_thinking_effort": entry["claude_thinking_effort"],
            "checked_at": time.time(),
            "models_by_upstream": models_by_upstream,
        }
    )


def list_models_for_item_detail(it: dict) -> dict:
    url = str((it or {}).get("url") or "").strip()
    api_key = str((it or {}).get("api_key") or "").strip()
    if not url:
        return {"ok": False, "models": [], "status": 0, "source": "", "error": "URL 为空"}
    if is_openrouter_url(url):
        models = openrouter_model_options()
        return {
            "ok": bool(models),
            "models": models,
            "status": 200 if models else 0,
            "source": "openrouter_model_options",
            "error": "" if models else "OPENROUTER_FIXED_MODEL/OPENROUTER_EXTRA_MODELS 未配置",
        }
    if is_siliconflow_url(url):
        models = siliconflow_model_options()
        if not models:
            return {
                "ok": False,
                "models": [],
                "status": 0,
                "source": "siliconflow_model_options",
                "error": "SILICONFLOW_MODELS 未配置",
            }
        return {
            "ok": True,
            "models": models,
            "status": 200,
            "source": "siliconflow_model_options",
            "error": "",
        }
    if is_cloudflare_anthropic_url(url):
        models = cloudflare_claude_model_options(url)
        return {
            "ok": bool(models),
            "models": models,
            "status": 200 if models else 0,
            "source": "cloudflare_claude_model_options",
            "error": "" if models else "CLOUDFLARE_CLAUDE_MODELS 未配置",
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
        source = "upstream_v1_models"
        if is_pioneer_url(url):
            pioneer_models = pioneer_claude_model_options(out)
            out = pioneer_models
            source = "pioneer_claude_models"
        return {
            "ok": bool(out),
            "models": out,
            "status": int(resp.status_code or 0),
            "source": source,
            "error": "" if out else ("Pioneer 未返回 Claude 短模型名" if is_pioneer_url(url) else "上游 /v1/models 返回空列表"),
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


def get_cached_active_model(refresh_if_missing: bool = False) -> str:
    payload = _load_active_model_payload()
    active, item, url, key = _current_active_context()
    if url:
        entry = _active_model_entry_from_payload(payload, active, item, url, key)
        model = str(entry.get("model") or "").strip() if isinstance(entry, dict) else ""
        if model:
            return model
    # refresh_if_missing is kept for old call sites, but backend runtime must not
    # guess or refresh the active model by itself. The model cache changes only
    # through explicit model save.
    return ""


def set_active_model(model: str) -> bool:
    model = str(model or "").strip()
    if not model:
        return False
    active, item, url, key = _current_active_context()
    if not url:
        return False
    effort = get_active_claude_thinking_effort()
    payload = _load_active_model_payload()
    models_by_upstream = dict(payload.get("models_by_upstream") or {}) if isinstance(payload.get("models_by_upstream"), dict) else {}
    entry = {
        "active": active,
        "url": url,
        "upstream_key": key,
        "model": model,
        "claude_thinking_effort": effort,
        "checked_at": time.time(),
    }
    if key:
        models_by_upstream[key] = entry
    return _save_active_model_payload(
        {
            "active": active,
            "url": url,
            "upstream_key": key,
            "model": model,
            "claude_thinking_effort": effort,
            "checked_at": time.time(),
            "models_by_upstream": models_by_upstream,
        }
    )


def set_active(index: int) -> bool:
    data = load_upstreams()
    items = data.get("items") or []
    if index < 0 or index >= len(items):
        return False
    data["active"] = int(index)
    return save_upstreams(data)


def get_active_item() -> dict | None:
    data = load_upstreams()
    items = data.get("items") or []
    idx = int(data.get("active") or 0)
    if not items or idx < 0 or idx >= len(items):
        return None
    return items[idx]
