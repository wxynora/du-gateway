import logging
import os
from urllib.parse import urlparse

import requests
from flask import jsonify, request

from config import (
    OPENROUTER_CACHE_CONTROL_TYPE,
    OPENROUTER_REASONING_MAX_TOKENS,
    OPENROUTER_VERBOSITY,
    is_openrouter_url,
    is_siliconflow_url,
    openrouter_model_options,
    siliconflow_model_options,
)
from storage import upstream_store


logger = logging.getLogger(__name__)


def _parsed_url(raw_url: str):
    raw = str(raw_url or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    try:
        return urlparse(raw)
    except Exception:
        return None


def _is_local_oauth_url(raw_url: str) -> bool:
    parsed = _parsed_url(raw_url)
    host = (parsed.hostname if parsed else "") or ""
    return host.lower() in {"127.0.0.1", "localhost", "::1"}


def _oauth_label_for_item(it: dict) -> str:
    name = str(it.get("name") or "").lower()
    url = str(it.get("url") or "").lower()
    parsed = _parsed_url(url)
    port = parsed.port if parsed else None
    joined = f"{name} {url}"
    if "claude" in joined or port == 8082:
        return "Claude Code"
    if "codex" in joined or "cpa" in joined or port == 8317:
        return "Codex"
    return "OAuth"


def _oauth_status_key(label: str) -> str:
    label_lower = label.lower()
    if "claude" in label_lower:
        names = ("CLAUDE_OAUTH_SYNC_KEY", "CLAUDE_PROXY_SYNC_KEY", "OAUTH_SYNC_KEY")
    elif "codex" in label_lower:
        names = ("CODEX_OAUTH_SYNC_KEY", "CODEX_PROXY_SYNC_KEY", "CODEX_TOKEN_SYNC_KEY", "OAUTH_SYNC_KEY")
    else:
        names = ("OAUTH_SYNC_KEY",)
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _sanitize_oauth_status(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    out: dict = {}
    if "ok" in data:
        out["ok"] = bool(data.get("ok"))
    if "stale" in data:
        out["stale"] = bool(data.get("stale"))
    expires_at = data.get("expiresAt", data.get("expires_at"))
    expires_in = data.get("expiresInSeconds", data.get("expires_in_seconds"))
    if expires_at is not None:
        out["expiresAt"] = expires_at
    if expires_in is not None:
        out["expiresInSeconds"] = expires_in
    source = str(data.get("source") or "").strip()
    if source:
        out["source"] = source
    rate_limit_snapshot = _sanitize_rate_limit_snapshot(data.get("rateLimitSnapshot"))
    if rate_limit_snapshot:
        out["rateLimitSnapshot"] = rate_limit_snapshot
    return out or None


def _sanitize_rate_limit_window(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    out: dict = {}
    status = str(data.get("status") or "").strip()
    if status:
        out["status"] = status
    for source_key, target_key in (("resetAt", "resetAt"), ("utilization", "utilization")):
        value = data.get(source_key)
        if value is not None:
            out[target_key] = value
    return out or None


def _sanitize_rate_limit_snapshot(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    out: dict = {}
    for key in (
        "updatedAt",
        "statusCode",
        "status",
        "resetAt",
        "representativeClaim",
        "fallbackPercentage",
        "overageStatus",
        "overageDisabledReason",
        "retryAfter",
    ):
        value = data.get(key)
        if value not in (None, ""):
            out[key] = value
    five_hour = _sanitize_rate_limit_window(data.get("fiveHour"))
    if five_hour:
        out["fiveHour"] = five_hour
    seven_day = _sanitize_rate_limit_window(data.get("sevenDay"))
    if seven_day:
        out["sevenDay"] = seven_day
    return out or None


def _oauth_status_key_candidates(it: dict, label: str) -> list[str]:
    candidates: list[str] = []
    env_key = _oauth_status_key(label)
    if env_key:
        candidates.append(env_key)
    upstream_key = str((it or {}).get("api_key") or "").strip()
    if upstream_key:
        candidates.append(upstream_key)
    out: list[str] = []
    seen: set[str] = set()
    for key in candidates:
        if key and key not in seen:
            out.append(key)
            seen.add(key)
    return out


def _oauth_status_for_item(it: dict, label: str) -> tuple[dict | None, str]:
    parsed = _parsed_url(str(it.get("url") or ""))
    if not parsed or not parsed.scheme or not parsed.netloc:
        return None, "url_invalid"
    keys = _oauth_status_key_candidates(it, label)
    if not keys:
        return None, "sync_key_missing"
    base = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    last_error = ""
    try:
        for key in keys:
            resp = requests.get(
                f"{base}/internal/oauth-status",
                headers={"X-OAuth-Sync-Key": key},
                timeout=1.0,
            )
            if not (200 <= resp.status_code < 300):
                last_error = f"http_{resp.status_code}"
                continue
            status = _sanitize_oauth_status(resp.json() if resp.content else {})
            return status, "" if status else "status_empty"
        return None, last_error or "request_failed"
    except Exception as e:
        logger.debug("oauth status unavailable label=%s url=%s err=%s", label, base, e)
        return None, "request_failed"


def _public_upstream_item(it: dict) -> dict:
    item = {"name": it.get("name") or "", "url": it.get("url") or ""}
    if _is_local_oauth_url(item["url"]):
        label = _oauth_label_for_item(it)
        status, status_error = _oauth_status_for_item(it, label)
        item["category"] = "oauth"
        item["oauth_label"] = label
        if status:
            item["oauth_status"] = status
        elif status_error:
            item["oauth_status_error"] = status_error
    else:
        item["category"] = "openai"
    return item


def _chat_url_to_models_url(chat_url: str) -> str:
    base = str(chat_url or "").strip().rstrip("/")
    if not base:
        return ""
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/") + "/v1/models"


def _probe_upstream_item(it: dict) -> dict:
    url = (it.get("url") or "").strip()
    name = (it.get("name") or "").strip()
    api_key = (it.get("api_key") or "").strip()
    out = {
        "name": name,
        "url": url,
        "models_ok": False,
        "chat_ok": False,
        "models_status": 0,
        "chat_status": 0,
        "model_count": 0,
        "error": "",
        "note": "",
        "status": "fail",
    }
    if not url:
        out["error"] = "URL 为空"
        return out

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    model_name = ""
    if is_openrouter_url(url):
        models = openrouter_model_options()
        model_name = models[0] if models else ""
        out["models_ok"] = True
        out["models_status"] = 200
        out["model_count"] = len(models)
        out["note"] = "OpenRouter 已固定模型，跳过 /v1/models 探测"
    elif is_siliconflow_url(url):
        models = siliconflow_model_options()
        model_name = models[0] if models else ""
        out["models_ok"] = bool(models)
        out["models_status"] = 200 if models else 0
        out["model_count"] = len(models)
        out["note"] = "SiliconFlow 已使用本地模型候选，跳过 /v1/models 探测" if models else "SiliconFlow 模型候选未配置"

    try:
        if not model_name:
            models_url = _chat_url_to_models_url(url)
            rm = requests.get(models_url, headers=headers, timeout=12)
            out["models_status"] = int(rm.status_code or 0)
            if rm.status_code >= 400:
                logger.warning(
                    "上游探活 models 异常 name=%s status=%s url=%s body=%s",
                    name or "(empty)",
                    rm.status_code,
                    models_url,
                    (rm.text or "")[:300],
                )
            if 200 <= rm.status_code < 300:
                data = rm.json() if rm.content else {}
                lst = data.get("data") if isinstance(data, dict) else None
                if isinstance(lst, list):
                    out["model_count"] = len(lst)
                    if lst:
                        first = lst[0]
                        if isinstance(first, dict):
                            model_name = str(first.get("id") or "").strip()
                        elif isinstance(first, str):
                            model_name = first.strip()
                out["models_ok"] = True
    except Exception as e:
        out["error"] = str(e)

    if not model_name:
        out["note"] = "models 未返回可用模型，已跳过 chat 探活"
        if out["models_ok"]:
            out["status"] = "degraded"
        return out

    try:
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_tokens": 8,
        }
        if is_openrouter_url(url):
            body["reasoning"] = {
                "enabled": True,
                "max_tokens": OPENROUTER_REASONING_MAX_TOKENS,
            }
            if OPENROUTER_VERBOSITY:
                body["verbosity"] = OPENROUTER_VERBOSITY
            if OPENROUTER_CACHE_CONTROL_TYPE:
                body["cache_control"] = {"type": OPENROUTER_CACHE_CONTROL_TYPE}
        chat_url = url
        rc = requests.post(chat_url, headers=headers, json=body, timeout=20)
        out["chat_status"] = int(rc.status_code or 0)
        if rc.status_code >= 400:
            logger.warning(
                "上游探活 chat 异常 name=%s status=%s model=%s url=%s body=%s",
                name or "(empty)",
                rc.status_code,
                model_name,
                chat_url,
                (rc.text or "")[:300],
            )
        if 200 <= rc.status_code < 300:
            out["chat_ok"] = True
    except Exception as e:
        msg = str(e)
        if "Read timed out" in msg and out["models_ok"]:
            out["note"] = "chat 探活超时（上游可能可用，但较慢）"
        elif not out["error"]:
            out["error"] = msg

    if out["chat_ok"] and out["models_ok"]:
        out["status"] = "ok"
    elif out["chat_ok"]:
        out["status"] = "degraded"
        if not out["note"]:
            out["note"] = "chat 可用，但 models 探测失败或上游未标准实现 /v1/models"
    elif out["models_ok"]:
        out["status"] = "degraded"
    return out


def register_routes(bp) -> None:
    @bp.route("/upstreams", methods=["GET"])
    def miniapp_get_upstreams():
        data = upstream_store.load_upstreams()
        model = upstream_store.get_cached_active_model(refresh_if_missing=False)
        claude_thinking_effort = upstream_store.get_active_claude_thinking_effort()
        codex_reasoning_effort = upstream_store.get_active_codex_reasoning_effort()
        items = [_public_upstream_item(it) for it in (data.get("items") or []) if isinstance(it, dict)]
        return jsonify(
            {
                "active": int(data.get("active") or 0),
                "model": model,
                "claude_thinking_effort": claude_thinking_effort,
                "claude_thinking_efforts": list(upstream_store.CLAUDE_THINKING_EFFORTS),
                "codex_reasoning_effort": codex_reasoning_effort,
                "codex_reasoning_efforts": list(upstream_store.CODEX_REASONING_EFFORTS),
                "items": items,
            }
        )

    @bp.route("/upstreams", methods=["PUT"])
    def miniapp_put_upstreams():
        data = request.get_json(silent=True) or {}
        active = int(data.get("active") or 0)
        ok = upstream_store.set_active(active)
        model = upstream_store.get_cached_active_model(refresh_if_missing=False) if ok else ""
        saved = upstream_store.load_upstreams()
        return jsonify(
            {
                "ok": ok,
                "active": int(saved.get("active") or 0),
                "model": model,
                "claude_thinking_effort": upstream_store.get_active_claude_thinking_effort(),
                "codex_reasoning_effort": upstream_store.get_active_codex_reasoning_effort(),
            }
        )

    @bp.route("/upstreams/active", methods=["PUT"])
    def miniapp_set_active_upstream():
        data = request.get_json(silent=True) or {}
        idx = int(data.get("active") or 0)
        ok = upstream_store.set_active(idx)
        model = upstream_store.get_cached_active_model(refresh_if_missing=False) if ok else ""
        saved = upstream_store.load_upstreams()
        return jsonify(
            {
                "ok": ok,
                "active": int(saved.get("active") or 0),
                "model": model,
                "claude_thinking_effort": upstream_store.get_active_claude_thinking_effort(),
                "codex_reasoning_effort": upstream_store.get_active_codex_reasoning_effort(),
            }
        )

    @bp.route("/upstreams/models", methods=["GET"])
    def miniapp_get_upstream_models():
        upstreams = upstream_store.load_upstreams()
        items = upstreams.get("items") or []
        active = int(upstreams.get("active") or 0)
        try:
            idx = int(request.args.get("index", active))
        except Exception:
            idx = active
        if idx < 0 or idx >= len(items):
            return jsonify({"ok": False, "error": "index 无效"}), 400
        detail = upstream_store.list_models_for_item_detail(items[idx])
        models = detail.get("models") or []
        model = upstream_store.get_cached_active_model(refresh_if_missing=False) if idx == active else ""
        ok = bool(detail.get("ok"))
        return jsonify(
            {
                "ok": ok,
                "active": active,
                "index": idx,
                "model": model,
                "models": models,
                "model_count": len(models),
                "status": int(detail.get("status") or 0),
                "source": detail.get("source") or "",
                "error": "" if ok else (detail.get("error") or "模型列表不可用"),
            }
        ), 200 if ok else 502

    @bp.route("/upstreams/model", methods=["PUT"])
    def miniapp_set_active_upstream_model():
        data = request.get_json(silent=True) or {}
        model = str(data.get("model") or "").strip()
        ok = upstream_store.set_active_model(model)
        saved_model = upstream_store.get_cached_active_model(refresh_if_missing=False) if ok else ""
        saved = upstream_store.load_upstreams()
        return jsonify(
            {
                "ok": ok,
                "active": int(saved.get("active") or 0),
                "model": saved_model,
                "claude_thinking_effort": upstream_store.get_active_claude_thinking_effort(),
                "codex_reasoning_effort": upstream_store.get_active_codex_reasoning_effort(),
                "error": "" if ok else "model 无效",
            }
        )

    @bp.route("/upstreams/claude-thinking-effort", methods=["PUT"])
    def miniapp_set_claude_thinking_effort():
        data = request.get_json(silent=True) or {}
        effort = upstream_store.normalize_claude_thinking_effort(str(data.get("effort") or ""))
        ok = upstream_store.set_active_claude_thinking_effort(effort)
        saved = upstream_store.load_upstreams()
        return jsonify(
            {
                "ok": ok,
                "active": int(saved.get("active") or 0),
                "effort": upstream_store.get_active_claude_thinking_effort(),
                "error": "" if ok else "active upstream 无效",
            }
        )

    @bp.route("/upstreams/codex-reasoning-effort", methods=["PUT"])
    def miniapp_set_codex_reasoning_effort():
        data = request.get_json(silent=True) or {}
        effort = upstream_store.normalize_codex_reasoning_effort(str(data.get("effort") or ""))
        model = upstream_store.get_cached_active_model(refresh_if_missing=False)
        if str(model or "").strip().lower() != "gpt-5.6-sol":
            return jsonify({"ok": False, "error": "仅 gpt-5.6-sol 支持此档位选择"}), 400
        ok = upstream_store.set_active_codex_reasoning_effort(effort)
        saved = upstream_store.load_upstreams()
        return jsonify(
            {
                "ok": ok,
                "active": int(saved.get("active") or 0),
                "effort": upstream_store.get_active_codex_reasoning_effort(),
                "error": "" if ok else "active upstream 无效",
            }
        )

    @bp.route("/upstreams/probe", methods=["POST"])
    def miniapp_probe_upstreams():
        data = request.get_json(silent=True) or {}
        idx = data.get("index", None)
        probe_all = bool(data.get("all"))
        upstreams = upstream_store.load_upstreams()
        items = upstreams.get("items") or []
        active = int(upstreams.get("active") or 0)

        targets: list[tuple[int, dict]] = []
        if probe_all:
            targets = [(i, it) for i, it in enumerate(items) if isinstance(it, dict)]
        else:
            try:
                i = int(idx if idx is not None else active)
            except Exception:
                i = active
            if i < 0 or i >= len(items):
                return jsonify({"ok": False, "error": "index 无效"}), 400
            targets = [(i, items[i])]

        results = []
        for i, it in targets:
            r = _probe_upstream_item(it)
            r["index"] = i
            r["isActive"] = i == active
            results.append(r)

        status = "ok"
        if any((x.get("status") == "fail") for x in results):
            status = "degraded" if any((x.get("status") == "ok") for x in results) else "fail"
        return jsonify({"ok": True, "status": status, "results": results, "count": len(results)})
