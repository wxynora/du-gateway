import json
from pathlib import Path

from config import DATA_DIR, TARGET_AI_URL, TARGET_AI_API_KEY, TARGET_AI_URLS, TARGET_AI_API_KEYS


UPSTREAMS_FILE = DATA_DIR / "upstreams.json"


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
    return {"active": 0, "items": items, "anthropic_prompt_caching_enabled": False}


def load_upstreams() -> dict:
    """
    开启“切换”模式时：items 永远来自环境变量（只允许切换 active）。
    files 里仅保存 active，避免手机端任意改 URL 列表。
    """
    payload = _default_payload()
    items = payload.get("items") or []
    if not UPSTREAMS_FILE.exists():
        return {"active": 0, "items": items, "anthropic_prompt_caching_enabled": False}
    try:
        with open(UPSTREAMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return {"active": 0, "items": items, "anthropic_prompt_caching_enabled": False}

    active = int(data.get("active") or 0)
    if active < 0 or active >= len(items):
        active = 0
    enabled = bool(data.get("anthropic_prompt_caching_enabled", False))
    return {"active": active, "items": items, "anthropic_prompt_caching_enabled": enabled}


def save_upstreams(payload: dict) -> bool:
    # 只保存 active，items 从 env 重新构建
    UPSTREAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(UPSTREAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "active": int(payload.get("active") or 0),
                    "anthropic_prompt_caching_enabled": bool(payload.get("anthropic_prompt_caching_enabled", False)),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        return True
    except Exception:
        return False


def set_active(index: int) -> bool:
    data = load_upstreams()
    items = data.get("items") or []
    if index < 0 or index >= len(items):
        return False
    data["active"] = int(index)
    data["anthropic_prompt_caching_enabled"] = False
    return save_upstreams(data)


def set_anthropic_prompt_caching_enabled(enabled: bool) -> bool:
    data = load_upstreams()
    data["anthropic_prompt_caching_enabled"] = bool(enabled)
    return save_upstreams(data)


def get_active_item() -> dict | None:
    data = load_upstreams()
    items = data.get("items") or []
    idx = int(data.get("active") or 0)
    if not items or idx < 0 or idx >= len(items):
        return None
    return items[idx]

