from __future__ import annotations

import base64

from flask import Blueprint, jsonify, request

from services.music_melody_analyzer import MusicMelodyError, analyze_music_melody
from storage.music_melody_store import get_music_melody_entry, list_music_melody_entries, save_music_melody_entry
from config import MUSIC_ANALYSIS_MODEL, MUSIC_ANALYSIS_PROVIDER, MUSIC_PROMPT_VERSION

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
    )
    if not entry:
        return jsonify({"ok": False, "error": "音乐分析结果保存失败"}), 500
    return jsonify({"ok": True, "entry": entry})
