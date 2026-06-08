import logging
import re
import time
from pathlib import Path

from flask import Response, jsonify, request, stream_with_context

from config import MINIAPP_LOG_FILE, QQ_ONEBOT_LOG_FILE, WECHAT_ILINK_LOG_FILE
from utils.log_reader import resolve_log_path, stream_logs_sse, tail_logs


sumitalk_logger = logging.getLogger("sumitalk")
_LOG_CATEGORIES = {"all", "proactive", "sumitalk", "wechat", "tgbot", "qq"}
_LOG_LINE_MAX_CHARS = 6000
_CLIENT_LOG_FIELD_MAX_CHARS = 180
_CLIENT_LOG_FIELD_MAX_COUNT = 24
_CLIENT_LOG_SENSITIVE_RE = re.compile(r"(token|secret|key|authorization|password|cookie)", re.I)


def _clip_log_line(line: str) -> str:
    text = str(line or "")
    if len(text) <= _LOG_LINE_MAX_CHARS:
        return text
    omitted = len(text) - _LOG_LINE_MAX_CHARS
    return f"{text[:_LOG_LINE_MAX_CHARS]} ...（日志单行过长，已截断 {omitted} 字）"


def _clip_sse_chunk(chunk: bytes) -> bytes:
    if not chunk.startswith(b"data: "):
        return chunk
    text = chunk.decode("utf-8", errors="replace")
    line = text[6:].rstrip("\n")
    return ("data: " + _clip_log_line(line) + "\n\n").encode("utf-8")


def _miniapp_log_category() -> str:
    category = str(request.args.get("category") or "all").strip().lower()
    if category not in _LOG_CATEGORIES:
        category = "all"
    return category


def _line_matches_log_category(line: str, category: str) -> bool:
    raw = str(line or "")
    if category == "all":
        return True
    if category == "proactive":
        return "[TGPro]" in raw or "主动发消息" in raw
    if category == "sumitalk":
        return "[SumiTalk]" in raw
    if category == "tgbot":
        return "[TGBot]" in raw
    if category == "wechat":
        return "[wechat-ilink]" in raw
    if category == "qq":
        return "[qq-onebot]" in raw
    return True


def _miniapp_log_source(category: str) -> tuple[str, str]:
    if category == "wechat":
        path = str(WECHAT_ILINK_LOG_FILE or "").strip()
        if not path:
            raise ValueError("未配置 WECHAT_ILINK_LOG_FILE")
        return path, "wechat"
    if category == "qq":
        path = str(QQ_ONEBOT_LOG_FILE or "").strip()
        if not path:
            raise ValueError("未配置 QQ_ONEBOT_LOG_FILE")
        return path, "qq"
    return str(MINIAPP_LOG_FILE or "").strip(), "gateway"


def _safe_client_log_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return str(value)
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text[:_CLIENT_LOG_FIELD_MAX_CHARS]


def _safe_client_log_fields(fields: dict) -> str:
    if not isinstance(fields, dict):
        return ""
    parts = []
    for key, value in list(fields.items())[:_CLIENT_LOG_FIELD_MAX_COUNT]:
        k = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(key or "").strip())[:50]
        if not k:
            continue
        if _CLIENT_LOG_SENSITIVE_RE.search(k):
            parts.append(f"{k}=<redacted>")
            continue
        parts.append(f"{k}={_safe_client_log_value(value)}")
    return " ".join(parts)


def register_routes(bp) -> None:
    @bp.route("/client-error", methods=["POST"])
    def miniapp_client_error():
        body = request.get_json(silent=True) or {}
        kind = str(body.get("kind") or "client_error").strip()[:80]
        message = str(body.get("message") or "").strip()[:1200]
        stack = str(body.get("stack") or "").strip()[:4000]
        href = str(body.get("href") or "").strip()[:500]
        ua = str(body.get("userAgent") or request.headers.get("User-Agent") or "").strip()[:500]
        source = str(body.get("source") or "").strip()[:300]
        line = str(body.get("line") or "").strip()[:40]
        column = str(body.get("column") or "").strip()[:40]
        component_stack = str(body.get("componentStack") or "").strip()[:2000]
        sumitalk_logger.warning(
            "client_error kind=%s message=%s href=%s source=%s line=%s column=%s ua=%s stack=%s component_stack=%s",
            kind,
            message,
            href,
            source,
            line,
            column,
            ua,
            stack,
            component_stack,
        )
        return jsonify({"ok": True})

    @bp.route("/logs/client", methods=["POST"])
    def miniapp_client_log():
        body = request.get_json(silent=True) or {}
        event = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(body.get("event") or "client_event").strip())[:80] or "client_event"
        level = str(body.get("level") or "info").strip().lower()
        fields = _safe_client_log_fields(body.get("fields") or {})
        message = "[SumiTalk] client_event event=%s %s"
        if level in {"error", "err"}:
            sumitalk_logger.error(message, event, fields)
        elif level in {"warning", "warn"}:
            sumitalk_logger.warning(message, event, fields)
        else:
            sumitalk_logger.info(message, event, fields)
        return jsonify({"ok": True})

    @bp.route("/logs", methods=["GET"])
    def miniapp_logs_tail():
        category = _miniapp_log_category()
        lines = request.args.get("lines", type=int, default=200)
        if lines < 1:
            lines = 1
        if lines > 2000:
            lines = 2000
        try:
            log_path, source_kind = _miniapp_log_source(category)
            out_lines = [
                _clip_log_line(line)
                for line in tail_logs(log_path, lines=lines, line_filter=lambda line: _line_matches_log_category(line, category))
            ]
            file_exists = False
            try:
                log_file = resolve_log_path(log_path)
                if log_file:
                    p = Path(log_file)
                    file_exists = p.exists()
            except Exception:
                file_exists = False
            return jsonify(
                {
                    "ok": True,
                    "category": category,
                    "file": log_path,
                    "lines": out_lines,
                    "count": len(out_lines),
                    "source": source_kind if file_exists else ("stdout" if source_kind == "gateway" else source_kind),
                }
            )
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e), "category": category}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/logs/stream", methods=["GET"])
    def miniapp_logs_stream():
        category = _miniapp_log_category()
        start_lines = request.args.get("start_lines", type=int, default=80)
        if start_lines < 0:
            start_lines = 0
        if start_lines > 500:
            start_lines = 500

        try:
            log_path, _source_kind = _miniapp_log_source(category)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e), "category": category}), 400

        def gen():
            yield b": ready\n\n"
            time.sleep(0.01)
            for chunk in stream_logs_sse(
                log_path,
                start_lines=start_lines,
                line_filter=lambda line: _line_matches_log_category(line, category),
            ):
                yield _clip_sse_chunk(chunk)

        return Response(
            stream_with_context(gen()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
