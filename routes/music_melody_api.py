from __future__ import annotations

import base64
import re
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request

from services.music_melody_analyzer import MusicMelodyError, analyze_music_melody
from storage.music_audio_store import get_music_audio, music_audio_content_type, save_music_audio
from storage.music_melody_store import (
    get_music_melody_entry,
    get_music_melody_entry_by_id,
    list_music_melody_entries,
    save_music_melody_entry,
    update_music_melody_audio,
)
from config import MUSIC_ANALYSIS_MODEL, MUSIC_ANALYSIS_PROVIDER, MUSIC_PROMPT_VERSION, MUSIC_AUDIO_MAX_BYTES

bp = Blueprint("music_melody_api", __name__)


def _bool_arg(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _form_or_json() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict(flat=True)


def _read_audio_from_request(data: dict) -> tuple[bytes, str, str]:
    f = request.files.get("audio") or request.files.get("file")
    if f:
        return f.read() or b"", f.filename or "music", f.mimetype or ""

    audio_b64 = str(data.get("audio_base64") or "").strip()
    if not audio_b64:
        return b"", "", ""
    if "," in audio_b64 and audio_b64.lower().startswith("data:"):
        header, audio_b64 = audio_b64.split(",", 1)
        mime = header.split(";", 1)[0].replace("data:", "").strip()
    else:
        mime = str(data.get("mime_type") or "").strip()
    try:
        return base64.b64decode(audio_b64), str(data.get("filename") or "music").strip(), mime
    except Exception:
        raise MusicMelodyError("audio_base64 不是有效 base64")


def _float_value(value: object) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _duration_from_entry(entry: dict) -> float:
    duration = _float_value((entry or {}).get("duration_seconds"))
    if duration > 0:
        return duration
    structured = (entry or {}).get("structured") if isinstance((entry or {}).get("structured"), dict) else {}
    segments = structured.get("segments") if isinstance(structured, dict) else []
    max_end = 0.0
    for segment in segments if isinstance(segments, list) else []:
        if not isinstance(segment, dict):
            continue
        max_end = max(max_end, _float_value(segment.get("end")))
    return max_end


def _cache_query_params() -> tuple[str, str, str, str, str]:
    title = str(request.args.get("title") or "").strip()
    artist = str(request.args.get("artist") or "").strip()
    provider = str(request.args.get("provider") or MUSIC_ANALYSIS_PROVIDER).strip() or MUSIC_ANALYSIS_PROVIDER
    model = str(request.args.get("model") or MUSIC_ANALYSIS_MODEL).strip() or MUSIC_ANALYSIS_MODEL
    prompt_version = str(request.args.get("prompt_version") or MUSIC_PROMPT_VERSION).strip() or MUSIC_PROMPT_VERSION
    return title, artist, provider, model, prompt_version


@bp.route("/api/music-melody/cache", methods=["GET"])
@bp.route("/api/music/listen/cache", methods=["GET"])
def music_melody_cache():
    title, artist, provider, model, prompt_version = _cache_query_params()
    if not title:
        return jsonify({"ok": False, "error": "缺少 title"}), 400
    entry = get_music_melody_entry(title, artist, provider, model, prompt_version)
    return jsonify({"ok": True, "hit": bool(entry), "entry": entry})


@bp.route("/api/music-melody/recent", methods=["GET"])
@bp.route("/api/music/listen/recent", methods=["GET"])
def music_melody_recent():
    limit = int(request.args.get("limit") or 50)
    return jsonify({"ok": True, "items": list_music_melody_entries(limit=limit)})


@bp.route("/api/music-melody/analyze", methods=["POST"])
@bp.route("/api/music/listen/analyze", methods=["POST"])
def music_melody_analyze():
    data = _form_or_json()
    title = str(data.get("title") or "").strip()
    artist = str(data.get("artist") or "").strip()
    model = str(data.get("model") or "").strip()
    prompt_version = str(data.get("prompt_version") or "").strip()
    duration_seconds = _float_value(data.get("duration_seconds"))
    lyrics_text = str(data.get("lyrics_text") or data.get("lyrics") or "").strip()
    force = _bool_arg(data.get("force"))
    try:
        audio_bytes, filename, mime_type = _read_audio_from_request(data)
        result = analyze_music_melody(
            title=title,
            artist=artist,
            audio_bytes=audio_bytes,
            filename=filename,
            mime_type=mime_type,
            force=force,
            model=model,
            prompt_version=prompt_version,
            duration_seconds=duration_seconds,
            lyrics_text=lyrics_text,
        )
        return jsonify(result)
    except MusicMelodyError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"音乐分析失败：{e}"}), 500


@bp.route("/api/music-melody/result", methods=["POST"])
@bp.route("/api/music/listen/result", methods=["POST"])
def music_melody_result():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    artist = str(data.get("artist") or "").strip()
    provider = str(data.get("provider") or MUSIC_ANALYSIS_PROVIDER).strip() or MUSIC_ANALYSIS_PROVIDER
    model = str(data.get("model") or MUSIC_ANALYSIS_MODEL).strip() or MUSIC_ANALYSIS_MODEL
    prompt_version = str(data.get("prompt_version") or MUSIC_PROMPT_VERSION).strip() or MUSIC_PROMPT_VERSION
    structured = data.get("structured") if isinstance(data.get("structured"), dict) else {}
    melody_text = str(data.get("melody_text") or data.get("display_text") or structured.get("display_text") or "").strip()
    overall_trend = str(data.get("overall_trend") or structured.get("overall_trend") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "缺少 title"}), 400
    if not melody_text:
        return jsonify({"ok": False, "error": "缺少 melody_text/display_text"}), 400
    entry = save_music_melody_entry(
        title=title,
        artist=artist,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        melody_text=melody_text,
        overall_trend=overall_trend,
        structured=structured,
        audio_key=str(data.get("audio_key") or "").strip(),
        audio_url=str(data.get("audio_url") or "").strip(),
        audio_format=str(data.get("audio_format") or "").strip(),
        audio_content_type=str(data.get("audio_content_type") or "").strip(),
        audio_size=int(_float_value(data.get("audio_size"))),
        duration_seconds=_float_value(data.get("duration_seconds")),
    )
    if not entry:
        return jsonify({"ok": False, "error": "音乐分析结果保存失败"}), 500
    return jsonify({"ok": True, "entry": entry})


@bp.route("/api/music-melody/audio", methods=["POST"])
@bp.route("/api/music/listen/audio", methods=["POST"])
def music_melody_audio_upload():
    data = _form_or_json()
    title = str(data.get("title") or request.form.get("title") or "").strip()
    artist = str(data.get("artist") or request.form.get("artist") or "").strip()
    provider = str(data.get("provider") or MUSIC_ANALYSIS_PROVIDER).strip() or MUSIC_ANALYSIS_PROVIDER
    model = str(data.get("model") or MUSIC_ANALYSIS_MODEL).strip() or MUSIC_ANALYSIS_MODEL
    prompt_version = str(data.get("prompt_version") or MUSIC_PROMPT_VERSION).strip() or MUSIC_PROMPT_VERSION
    if not title:
        return jsonify({"ok": False, "error": "缺少 title"}), 400
    f = request.files.get("audio") or request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "缺少 audio/file"}), 400

    entry = get_music_melody_entry(title, artist, provider, model, prompt_version)
    if not entry:
        return jsonify({"ok": False, "error": "未找到这首歌的分析缓存，请先写入分析结果"}), 404

    content = f.read() or b""
    if not content:
        return jsonify({"ok": False, "error": "音频文件为空"}), 400
    if len(content) > MUSIC_AUDIO_MAX_BYTES:
        mb = MUSIC_AUDIO_MAX_BYTES // 1024 // 1024
        return jsonify({"ok": False, "error": f"音频过大，最大 {mb}MB"}), 400

    saved = save_music_audio(
        cache_id=str(entry.get("id") or entry.get("cache_key") or ""),
        filename=f.filename or "music.mp3",
        content=content,
        content_type=f.mimetype or "",
    )
    if not saved:
        return jsonify({"ok": False, "error": "音频保存失败，请检查格式或 R2 配置"}), 400

    duration_seconds = _float_value(data.get("duration_seconds") or request.form.get("duration_seconds")) or _duration_from_entry(entry)
    updated = update_music_melody_audio(
        title,
        artist,
        provider,
        model,
        prompt_version,
        audio_key=str(saved.get("key") or ""),
        audio_url=str(saved.get("url") or ""),
        audio_format=str(saved.get("audio_format") or ""),
        audio_content_type=str(saved.get("content_type") or ""),
        audio_size=int(saved.get("size") or len(content)),
        duration_seconds=duration_seconds,
    )
    if not updated:
        return jsonify({"ok": False, "error": "音频已保存，但缓存元信息更新失败"}), 500
    return jsonify({"ok": True, "entry": updated, "audio": saved})


def _audio_response(data: bytes, content_type: str, filename: str) -> Response:
    size = len(data or b"")
    ctype = content_type or "audio/mpeg"
    safe_filename = quote(filename or "music.mp3")
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
        "Content-Disposition": f'inline; filename="{safe_filename}"',
    }
    range_header = str(request.headers.get("Range") or "").strip()
    if range_header:
        match = re.match(r"^bytes=(\d*)-(\d*)$", range_header)
        if match:
            start_raw, end_raw = match.groups()
            if start_raw == "" and end_raw:
                suffix_len = int(end_raw)
                start = max(0, size - suffix_len)
                end = size - 1
            else:
                start = int(start_raw or 0)
                end = int(end_raw) if end_raw else size - 1
            if start >= size or end < start:
                return Response(
                    b"",
                    status=416,
                    headers={**headers, "Content-Range": f"bytes */{size}"},
                    mimetype=ctype,
                )
            end = min(end, size - 1)
            chunk = data[start : end + 1]
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            headers["Content-Length"] = str(len(chunk))
            return Response(chunk, status=206, mimetype=ctype, headers=headers)
    headers["Content-Length"] = str(size)
    return Response(data, status=200, mimetype=ctype, headers=headers)


@bp.route("/api/music-melody/audio/<entry_id>.<ext>", methods=["GET"])
@bp.route("/api/music/listen/audio/<entry_id>.<ext>", methods=["GET"])
def music_melody_audio(entry_id: str, ext: str):
    entry = get_music_melody_entry_by_id(entry_id)
    if not entry:
        return Response(b"", status=404, mimetype="text/plain; charset=utf-8")
    audio_key = str(entry.get("audio_key") or "").strip()
    audio_format = str(entry.get("audio_format") or "").strip().lower()
    requested_ext = str(ext or "").strip().lower()
    if not audio_key or not audio_format or audio_format != requested_ext:
        return Response(b"", status=404, mimetype="text/plain; charset=utf-8")
    data, content_type = get_music_audio(audio_key)
    if not data:
        return Response(b"", status=404, mimetype="text/plain; charset=utf-8")
    filename = f"{entry.get('title') or 'music'}.{audio_format}"
    return _audio_response(
        data,
        content_type or str(entry.get("audio_content_type") or "") or music_audio_content_type(audio_format),
        filename,
    )
