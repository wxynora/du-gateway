import os
import re
import time
from pathlib import Path

import requests
from flask import jsonify

from config import MINIAPP_LOG_FILE, QQ_PROACTIVE_PUSH_URL, WECHAT_PROACTIVE_PUSH_URL
from storage import r2_store
from utils.log_reader import resolve_log_path
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing


def _diag_item(key: str, label: str, status: str, detail: str, **extra) -> dict:
    st = status if status in {"ok", "warn", "error"} else "warn"
    return {
        "key": key,
        "label": label,
        "status": st,
        "ok": st == "ok",
        "detail": str(detail or ""),
        **extra,
    }


def _format_bytes(num: int | float) -> str:
    try:
        value = float(num)
    except Exception:
        value = 0.0
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(value)}{units[idx]}"
    return f"{value:.1f}{units[idx]}"


def _format_diag_elapsed(iso_str: str) -> str:
    dt = parse_iso_to_beijing(str(iso_str or "").strip())
    now_dt = parse_iso_to_beijing(now_beijing_iso())
    if not dt or not now_dt:
        return ""
    seconds = max(0, int((now_dt - dt).total_seconds()))
    if seconds < 90:
        return "刚刚"
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes}分钟前"
    hours = minutes // 60
    rest = minutes % 60
    if hours < 24:
        return f"{hours}小时{rest}分钟前" if rest else f"{hours}小时前"
    days = hours // 24
    return f"{days}天前"


def _diag_http_json(method: str, url: str, **kwargs) -> tuple[bool, int, dict | None, str, float]:
    start = time.time()
    try:
        if method.upper() == "POST":
            resp = requests.post(url, timeout=kwargs.pop("timeout", 1.8), **kwargs)
        else:
            resp = requests.get(url, timeout=kwargs.pop("timeout", 1.8), **kwargs)
        elapsed_ms = (time.time() - start) * 1000
        text = resp.text[:500]
        try:
            data = resp.json()
        except Exception:
            data = None
        return resp.ok, int(resp.status_code), data, text, elapsed_ms
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return False, 0, None, str(e), elapsed_ms


def _diag_push_health_base(push_url: str, fallback: str) -> str:
    raw = str(push_url or "").strip() or fallback
    return re.sub(r"/push/?$", "", raw.rstrip("/"))


def _diag_count_processes(*needles: str) -> int:
    proc_dir = Path("/proc")
    if not proc_dir.exists():
        return 0
    count = 0
    lowered = [str(n or "").lower() for n in needles if str(n or "").strip()]
    for item in proc_dir.iterdir():
        if not item.name.isdigit():
            continue
        try:
            raw = (item / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
        except Exception:
            continue
        if raw and all(n in raw for n in lowered):
            count += 1
    return count


def _diag_latest_sense_time(sense: dict) -> tuple[str, str]:
    best = ""
    best_bucket = ""
    for bucket, data in (sense or {}).items():
        if not isinstance(data, dict):
            continue
        for key in ("updatedAt", "observedAt", "capturedAt", "occurredAt"):
            val = str(data.get(key) or "").strip()
            if not val:
                continue
            dt = parse_iso_to_beijing(val)
            cur = parse_iso_to_beijing(best)
            if dt and (not cur or dt > cur):
                best = val
                best_bucket = str(bucket)
    return best, best_bucket


def _build_miniapp_diagnostics() -> list[dict]:
    items: list[dict] = []

    items.append(_diag_item("gateway", "网关进程", "ok", "当前请求已由 Web API 正常处理"))

    gunicorn_count = _diag_count_processes("gunicorn", "app:app")
    flask_dev_count = _diag_count_processes("app.py")
    if gunicorn_count > 0:
        status = "ok"
    else:
        status = "ok" if flask_dev_count == 1 else "warn" if flask_dev_count > 1 else "error"
    items.append(
        _diag_item(
            "gateway_process_count",
            "网关进程数",
            status,
            f"gunicorn={gunicorn_count} · app.py={flask_dev_count}",
        )
    )

    proactive_count = _diag_count_processes("run_telegram_proactive.py")
    status = "ok" if proactive_count == 1 else "warn" if proactive_count > 1 else "error"
    items.append(_diag_item("proactive_process", "主动消息调度", status, f"进程数={proactive_count}"))

    log_path = resolve_log_path(MINIAPP_LOG_FILE)
    try:
        size = Path(log_path).stat().st_size if log_path else 0
        if size <= 50 * 1024 * 1024:
            status = "ok"
        elif size <= 150 * 1024 * 1024:
            status = "warn"
        else:
            status = "error"
        items.append(_diag_item("gateway_log", "网关日志", status, f"{_format_bytes(size)}", path=log_path))
    except Exception as e:
        items.append(_diag_item("gateway_log", "网关日志", "warn", f"读取失败：{e}", path=log_path))

    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used_ratio = 1 - (free / total) if total > 0 else 0
        pct = round(used_ratio * 100, 1)
        status = "ok" if pct < 80 else "warn" if pct < 92 else "error"
        items.append(_diag_item("disk", "系统盘", status, f"已用 {pct}% · 可用 {_format_bytes(free)}"))
    except Exception as e:
        items.append(_diag_item("disk", "系统盘", "warn", f"读取失败：{e}"))

    try:
        sense = r2_store.get_sense_latest() or {}
        bucket_count = len([k for k, v in sense.items() if isinstance(v, dict)])
        status = "ok" if bucket_count > 0 else "warn"
        items.append(_diag_item("r2_sense", "R2 感知读取", status, f"sense/latest 有 {bucket_count} 个桶"))
        latest_at, latest_bucket = _diag_latest_sense_time(sense)
        elapsed = _format_diag_elapsed(latest_at)
        dt = parse_iso_to_beijing(latest_at)
        now_dt = parse_iso_to_beijing(now_beijing_iso())
        age_s = int((now_dt - dt).total_seconds()) if dt and now_dt else 999999
        if not latest_at:
            status = "warn"
            detail = "没有最近上报时间"
        else:
            status = "ok" if age_s <= 180 else "warn" if age_s <= 1800 else "error"
            detail = f"{latest_bucket} {elapsed}更新"
        items.append(_diag_item("device_sense", "手机感知", status, detail, latest_at=latest_at, bucket=latest_bucket))
    except Exception as e:
        items.append(_diag_item("r2_sense", "R2 感知读取", "error", f"读取失败：{e}"))

    qq_base = _diag_push_health_base(QQ_PROACTIVE_PUSH_URL, "http://127.0.0.1:8092")
    ok, code, data, text, elapsed = _diag_http_json("GET", f"{qq_base}/health")
    status = "ok" if ok and (not isinstance(data, dict) or data.get("ok") is not False) else "error"
    detail = f"HTTP {code} · {elapsed:.0f}ms" if code else text[:120]
    items.append(_diag_item("qq_connector", "QQ Connector", status, detail))

    onebot_base = os.environ.get("QQ_ONEBOT_API_BASE", "http://127.0.0.1:3000").strip().rstrip("/")
    onebot_token = os.environ.get("QQ_ONEBOT_API_TOKEN", "").strip()
    headers = {"Content-Type": "application/json"}
    if onebot_token:
        headers["Authorization"] = f"Bearer {onebot_token}"
    ok, code, data, text, elapsed = _diag_http_json("POST", f"{onebot_base}/get_login_info", headers=headers, json={})
    if isinstance(data, dict) and int(data.get("retcode") or 0) == 0:
        status = "ok"
        nickname = str((data.get("data") or {}).get("nickname") or "").strip()
        detail = f"已登录 {nickname}" if nickname else f"已登录 · {elapsed:.0f}ms"
    elif "token verify failed" in text.lower():
        status = "warn"
        detail = "OneBot 活着，但诊断未拿到 API token"
    else:
        status = "error"
        detail = f"HTTP {code} · {text[:120]}" if code else text[:120]
    items.append(_diag_item("napcat_onebot", "NapCat / OneBot", status, detail))

    wechat_base = _diag_push_health_base(WECHAT_PROACTIVE_PUSH_URL, "http://127.0.0.1:8091")
    ok, code, data, text, elapsed = _diag_http_json("GET", f"{wechat_base}/health")
    status = "ok" if ok and (not isinstance(data, dict) or data.get("ok") is not False) else "error"
    detail = f"HTTP {code} · {elapsed:.0f}ms" if code else text[:120]
    items.append(_diag_item("wechat_connector", "微信 Connector", status, detail))

    return items


def register_routes(bp) -> None:
    @bp.route("/diagnostics", methods=["GET"])
    def miniapp_diagnostics():
        items = _build_miniapp_diagnostics()
        has_error = any(str(item.get("status")) == "error" for item in items)
        has_warn = any(str(item.get("status")) == "warn" for item in items)
        return jsonify(
            {
                "ok": not has_error,
                "status": "error" if has_error else "warn" if has_warn else "ok",
                "generated_at": now_beijing_iso(),
                "items": items,
            }
        )
