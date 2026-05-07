import logging

import requests
from flask import jsonify, request

from config import (
    OPENROUTER_ALLOW_FALLBACKS,
    OPENROUTER_CACHE_CONTROL_TYPE,
    OPENROUTER_FIXED_MODEL,
    OPENROUTER_PROVIDER_ORDER,
    OPENROUTER_REASONING_MAX_TOKENS,
    OPENROUTER_VERBOSITY,
    is_openrouter_url,
)
from storage import upstream_store


logger = logging.getLogger(__name__)


def _chat_url_to_models_url(chat_url: str) -> str:
    base = (chat_url or "").strip().rstrip("/")
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
        model_name = OPENROUTER_FIXED_MODEL
        out["models_ok"] = True
        out["models_status"] = 200
        out["model_count"] = 1 if model_name else 0
        out["note"] = "OpenRouter 已固定模型，跳过 /v1/models 探测"

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
            if OPENROUTER_PROVIDER_ORDER:
                body["provider"] = {
                    "order": OPENROUTER_PROVIDER_ORDER,
                    "allow_fallbacks": OPENROUTER_ALLOW_FALLBACKS,
                }
            if OPENROUTER_CACHE_CONTROL_TYPE:
                body["cache_control"] = {"type": OPENROUTER_CACHE_CONTROL_TYPE}
        rc = requests.post(url, headers=headers, json=body, timeout=20)
        out["chat_status"] = int(rc.status_code or 0)
        if rc.status_code >= 400:
            logger.warning(
                "上游探活 chat 异常 name=%s status=%s model=%s url=%s body=%s",
                name or "(empty)",
                rc.status_code,
                model_name,
                url,
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
        items = [
            {"name": it.get("name") or "", "url": it.get("url") or ""}
            for it in (data.get("items") or [])
        ]
        return jsonify(
            {
                "active": int(data.get("active") or 0),
                "model": model,
                "items": items,
            }
        )

    @bp.route("/upstreams", methods=["PUT"])
    def miniapp_put_upstreams():
        data = request.get_json(silent=True) or {}
        active = int(data.get("active") or 0)
        ok = upstream_store.set_active(active)
        model = upstream_store.refresh_active_model_cache() if ok else ""
        saved = upstream_store.load_upstreams()
        return jsonify(
            {
                "ok": ok,
                "active": int(saved.get("active") or 0),
                "model": model,
            }
        )

    @bp.route("/upstreams/active", methods=["PUT"])
    def miniapp_set_active_upstream():
        data = request.get_json(silent=True) or {}
        idx = int(data.get("active") or 0)
        ok = upstream_store.set_active(idx)
        model = upstream_store.refresh_active_model_cache() if ok else ""
        saved = upstream_store.load_upstreams()
        return jsonify(
            {
                "ok": ok,
                "active": int(saved.get("active") or 0),
                "model": model,
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
        models = upstream_store.list_models_for_item(items[idx])
        model = upstream_store.get_cached_active_model(refresh_if_missing=False) if idx == active else ""
        return jsonify(
            {
                "ok": True,
                "active": active,
                "index": idx,
                "model": model,
                "models": models,
            }
        )

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
                "error": "" if ok else "model 无效",
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
