from __future__ import annotations

import base64
import json
import re
from urllib.parse import quote

from flask import Blueprint, Response, current_app, jsonify, request

from services.music_melody_analyzer import MusicMelodyError, analyze_music_melody
from services.music_lyrics import normalize_lyrics_payload, parse_lyrics_text
from storage import upstream_store
from storage.music_audio_store import get_music_audio, music_audio_content_type, save_music_audio
from storage.music_melody_store import (
    get_music_melody_entry,
    get_music_melody_entry_by_id,
    list_music_melody_entries,
    save_music_melody_entry,
    update_music_melody_audio,
    update_music_melody_lyrics_by_id,
)
from config import MUSIC_ANALYSIS_MODEL, MUSIC_ANALYSIS_PROVIDER, MUSIC_PROMPT_VERSION, MUSIC_AUDIO_MAX_BYTES

bp = Blueprint("music_melody_api", __name__)
SUMITALK_MAIN_WINDOW_ID = "sumitalk-main"


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


def _format_clock(seconds: float) -> str:
    total = max(0, int(round(float(seconds or 0))))
    return f"{total // 60}:{str(total % 60).zfill(2)}"


def _cache_query_params() -> tuple[str, str, str, str, str]:
    title = str(request.args.get("title") or "").strip()
    artist = str(request.args.get("artist") or "").strip()
    provider = str(request.args.get("provider") or MUSIC_ANALYSIS_PROVIDER).strip() or MUSIC_ANALYSIS_PROVIDER
    model = str(request.args.get("model") or MUSIC_ANALYSIS_MODEL).strip() or MUSIC_ANALYSIS_MODEL
    prompt_version = str(request.args.get("prompt_version") or MUSIC_PROMPT_VERSION).strip() or MUSIC_PROMPT_VERSION
    return title, artist, provider, model, prompt_version


def _extract_chat_completion_result(result) -> tuple[int, dict]:
    response = result
    status = 200
    if isinstance(result, tuple):
        response = result[0] if result else None
        for item in result[1:]:
            if isinstance(item, int):
                status = item
                break
    if hasattr(response, "status_code"):
        try:
            status = int(response.status_code)
        except Exception:
            pass
    data = None
    if hasattr(response, "get_json"):
        try:
            data = response.get_json(silent=True)
        except Exception:
            data = None
    if data is None and hasattr(response, "get_data"):
        try:
            text = response.get_data(as_text=True)
            data = json.loads(text) if text else {}
        except Exception:
            data = {"raw": response.get_data(as_text=True) if hasattr(response, "get_data") else ""}
    if not isinstance(data, dict):
        data = {"content": data}
    return status, data


def _extract_assistant_content(resp_json: dict) -> str:
    choices = resp_json.get("choices") if isinstance(resp_json, dict) else None
    if not (isinstance(choices, list) and choices and isinstance(choices[0], dict)):
        return ""
    msg = ((choices[0] or {}).get("message") or {})
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return ""


def _clip_text(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _segment_for_time(entry: dict, current_time: float) -> dict:
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    segments = structured.get("segments") if isinstance(structured, dict) else []
    if not isinstance(segments, list):
        return {}
    current = max(0.0, float(current_time or 0))
    fallback = {}
    for item in segments:
        if not isinstance(item, dict):
            continue
        start = _float_value(item.get("start"))
        end = _float_value(item.get("end"))
        if end > start:
            fallback = item
            if start <= current < end:
                return item
    return fallback


def _segments_until_time(entry: dict, current_time: float, current_segment: dict | None = None) -> list[dict]:
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    segments = structured.get("segments") if isinstance(structured, dict) else []
    current = max(0.0, float(current_time or 0))
    out: list[dict] = []
    seen = set()
    for item in segments if isinstance(segments, list) else []:
        if not isinstance(item, dict):
            continue
        start = _float_value(item.get("start"))
        end = _float_value(item.get("end"))
        if end <= start or start > current + 0.15:
            continue
        key = (round(start, 3), round(end, 3), str(item.get("section") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    if isinstance(current_segment, dict) and current_segment:
        start = _float_value(current_segment.get("start"))
        end = _float_value(current_segment.get("end"))
        key = (round(start, 3), round(end, 3), str(current_segment.get("section") or ""))
        if end > start and start <= current + 0.15 and key not in seen:
            out.append(current_segment)
    out.sort(key=lambda item: (_float_value(item.get("start")), _float_value(item.get("end"))))
    return out


def _format_segment_context_line(segment: dict, current_time: float) -> str:
    start = _float_value(segment.get("start"))
    end = _float_value(segment.get("end"))
    section = _clip_text(segment.get("section"), 60) or "这一段"
    current = start <= max(0.0, float(current_time or 0)) < end if end > start else False
    head = f"- {_format_clock(start)}-{_format_clock(end)} {section}" + ("（当前）" if current else "")
    details = []
    plain = _clip_text(segment.get("plain"), 360)
    melody = _clip_text(segment.get("melody_motion"), 260)
    sonic = _clip_text(segment.get("sonic_detail"), 260)
    intensity = _clip_text(segment.get("intensity"), 220)
    if plain:
        details.append(f"听感：{plain}")
    if melody:
        details.append(f"旋律/走向：{melody}")
    if sonic:
        details.append(f"声音细节：{sonic}")
    if intensity:
        details.append(f"强度/情绪推进：{intensity}")
    if not details:
        return head
    return head + "：" + "；".join(details)


def _lyrics_for_time(entry: dict, current_time: float) -> list[str]:
    lyrics = normalize_lyrics_payload(entry.get("lyrics")) if entry.get("lyrics") else {}
    raw_lines = lyrics.get("lines") if isinstance(lyrics, dict) else []
    if not isinstance(raw_lines, list):
        return []
    clean_lines = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        text = _clip_text(item.get("text"), 180)
        if not text:
            continue
        translation = _clip_text(item.get("translation"), 180)
        clean_lines.append(
            {
                "time": _float_value(item.get("time")),
                "text": text + (f"（{translation}）" if translation else ""),
            }
        )
    if not clean_lines:
        return []
    clean_lines.sort(key=lambda item: item["time"])
    active = 0
    t = max(0.0, float(current_time or 0))
    for idx, item in enumerate(clean_lines):
        if item["time"] <= t + 0.15:
            active = idx
        else:
            break
    start = max(0, active - 1)
    return [item["text"] for item in clean_lines[start : active + 2]]


def _lyrics_context_for_time(entry: dict, current_time: float) -> str:
    lyrics = normalize_lyrics_payload(entry.get("lyrics")) if entry.get("lyrics") else {}
    raw_lines = lyrics.get("lines") if isinstance(lyrics, dict) else []
    plain_lines = lyrics.get("plain_lines") if isinstance(lyrics, dict) else []
    clean_lines = []
    for item in raw_lines if isinstance(raw_lines, list) else []:
        if not isinstance(item, dict):
            continue
        text = _clip_text(item.get("text"), 180)
        if not text:
            continue
        translation = _clip_text(item.get("translation"), 180)
        clean_lines.append(
            {
                "time": _float_value(item.get("time")),
                "text": text + (f"（{translation}）" if translation else ""),
            }
        )
    if clean_lines:
        clean_lines.sort(key=lambda item: item["time"])
        active = 0
        t = max(0.0, float(current_time or 0))
        for idx, item in enumerate(clean_lines):
            if item["time"] <= t + 0.15:
                active = idx
            else:
                break
        past = [f"- {_format_clock(item['time'])} {item['text']}" for item in clean_lines[: active + 1]]
        while len("\n".join(past)) > 4200 and len(past) > 14:
            past.pop(0)
        if past and past[0] != f"- {_format_clock(clean_lines[0]['time'])} {clean_lines[0]['text']}":
            past.insert(0, "- ...")
        upcoming = [f"- {_format_clock(item['time'])} {item['text']}" for item in clean_lines[active + 1 : active + 4]]
        parts = []
        if past:
            parts.append("从开头到当前已唱到的歌词：\n" + "\n".join(past))
        if upcoming:
            parts.append("接下来几句歌词：\n" + "\n".join(upcoming))
        return "\n".join(parts).strip()

    clean_plain = [_clip_text(item, 180) for item in plain_lines if _clip_text(item, 180)]
    if not clean_plain:
        return ""
    text = "\n".join(f"- {line}" for line in clean_plain[:80])
    return "歌词文本：\n" + _clip_text(text, 5200)


def _sanitize_recent_listen_messages(items: object) -> list[dict]:
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role == "du":
            role = "assistant"
        if role not in {"user", "assistant"}:
            continue
        content = _clip_text(item.get("content") or item.get("text"), 1000)
        if not content:
            continue
        out.append({"role": role, "content": content})
    return out[-8:]


def _build_listen_context_system(entry: dict, segment: dict, current_time: float, duration: float) -> str:
    title = _clip_text(entry.get("title"), 80)
    artist = _clip_text(entry.get("artist"), 80)
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    overall = _clip_text(entry.get("overall_trend") or structured.get("overall_trend"), 700)
    heard_segments = _segments_until_time(entry, current_time, segment if isinstance(segment, dict) else None)
    current_lyrics = _lyrics_for_time(entry, current_time)
    lyrics_context = _lyrics_context_for_time(entry, current_time)
    lines = [
        "你正在和小玥一起听歌。",
        "",
        "【一起听上下文】",
        f"歌曲：{title or '未知歌曲'}" + (f" / {artist}" if artist else ""),
        f"当前播放：{_format_clock(current_time)}" + (f" / {_format_clock(duration)}" if duration > 0 else ""),
    ]
    if heard_segments:
        lines.append("从开头到当前已听到的音乐文字：")
        lines.extend(_format_segment_context_line(item, current_time) for item in heard_segments)
    if lyrics_context:
        lines.append(lyrics_context)
    elif current_lyrics:
        lines.append("当前歌词：" + " / ".join(current_lyrics))
    if overall:
        lines.append(f"整首歌的走向：{overall}")
    return "\n".join(lines).strip()


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
    lyrics_raw = data.get("lyrics_text") or data.get("lyrics_raw")
    lyrics_text = lyrics_raw.strip() if isinstance(lyrics_raw, str) else ""
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
    duration_seconds = _float_value(data.get("duration_seconds"))
    lyrics_raw = data.get("lyrics_text") or data.get("lyrics_raw")
    lyrics = None
    if isinstance(lyrics_raw, str) and lyrics_raw.strip():
        lyrics = parse_lyrics_text(lyrics_raw, duration_seconds=duration_seconds)
    elif "lyrics" in data:
        lyrics = normalize_lyrics_payload(data.get("lyrics"))
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
        lyrics=lyrics,
        audio_key=str(data.get("audio_key") or "").strip(),
        audio_url=str(data.get("audio_url") or "").strip(),
        audio_format=str(data.get("audio_format") or "").strip(),
        audio_content_type=str(data.get("audio_content_type") or "").strip(),
        audio_size=int(_float_value(data.get("audio_size"))),
        duration_seconds=duration_seconds,
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


@bp.route("/api/music-melody/lyrics", methods=["POST"])
@bp.route("/api/music/listen/lyrics", methods=["POST"])
def music_melody_lyrics_upload():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400
    entry_id = str(data.get("entry_id") or data.get("id") or "").strip()
    if not entry_id:
        title = str(data.get("title") or "").strip()
        artist = str(data.get("artist") or "").strip()
        provider = str(data.get("provider") or MUSIC_ANALYSIS_PROVIDER).strip() or MUSIC_ANALYSIS_PROVIDER
        model = str(data.get("model") or MUSIC_ANALYSIS_MODEL).strip() or MUSIC_ANALYSIS_MODEL
        prompt_version = str(data.get("prompt_version") or MUSIC_PROMPT_VERSION).strip() or MUSIC_PROMPT_VERSION
        entry = get_music_melody_entry(title, artist, provider, model, prompt_version) if title else None
        entry_id = str((entry or {}).get("id") or "").strip()
    if not entry_id:
        return jsonify({"ok": False, "error": "未找到这首歌的分析缓存"}), 404

    duration_seconds = _float_value(data.get("duration_seconds"))
    lyrics_raw = data.get("lyrics_text") or data.get("lyrics_raw")
    if isinstance(lyrics_raw, str) and lyrics_raw.strip():
        lyrics = parse_lyrics_text(lyrics_raw, duration_seconds=duration_seconds)
    else:
        lyrics = normalize_lyrics_payload(data.get("lyrics"))
    if not lyrics.get("lines") and not lyrics.get("plain_lines"):
        return jsonify({"ok": False, "error": "缺少歌词内容"}), 400
    entry = update_music_melody_lyrics_by_id(entry_id, lyrics)
    if not entry:
        return jsonify({"ok": False, "error": "歌词保存失败"}), 500
    return jsonify({"ok": True, "entry": entry, "lyrics": entry.get("lyrics") or {}})


@bp.route("/api/music/listen/chat", methods=["POST"])
def music_listen_chat():
    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400

    text = _clip_text(body.get("message") or body.get("text"), 2000)
    if not text:
        return jsonify({"ok": False, "error": "缺少 message"}), 400

    entry_id = str(body.get("entry_id") or body.get("id") or "").strip()
    entry = get_music_melody_entry_by_id(entry_id) if entry_id else None
    if not entry:
        title = str(body.get("title") or "").strip()
        artist = str(body.get("artist") or "").strip()
        provider = str(body.get("provider") or MUSIC_ANALYSIS_PROVIDER).strip() or MUSIC_ANALYSIS_PROVIDER
        model_key = str(body.get("analysis_model") or MUSIC_ANALYSIS_MODEL).strip() or MUSIC_ANALYSIS_MODEL
        prompt_version = str(body.get("prompt_version") or MUSIC_PROMPT_VERSION).strip() or MUSIC_PROMPT_VERSION
        entry = get_music_melody_entry(title, artist, provider, model_key, prompt_version) if title else None
    if not entry:
        return jsonify({"ok": False, "error": "未找到这首歌的分析缓存"}), 404

    if "lyrics" in body:
        client_lyrics = normalize_lyrics_payload(body.get("lyrics"))
        if client_lyrics.get("lines") or client_lyrics.get("plain_lines"):
            entry = {**entry, "lyrics": client_lyrics}

    model = str(body.get("model") or "").strip() or upstream_store.get_cached_active_model(refresh_if_missing=True)
    if not model:
        return jsonify({"ok": False, "error": "当前未设置全局模型"}), 502

    current_time = _float_value(body.get("current_time") or body.get("currentTime"))
    duration = _float_value(body.get("duration_seconds")) or _duration_from_entry(entry)
    client_segment = body.get("segment") if isinstance(body.get("segment"), dict) else {}
    segment = client_segment or _segment_for_time(entry, current_time)
    panel_payload = request.environ.get("miniapp_panel_payload") if isinstance(request.environ.get("miniapp_panel_payload"), dict) else {}
    panel_device_id = str((panel_payload or {}).get("device_id") or "").strip()
    window_id = str(body.get("window_id") or request.headers.get("X-Window-Id") or "").strip()
    if not window_id or window_id.startswith("music_listen"):
        window_id = SUMITALK_MAIN_WINDOW_ID
    reply_target = str(body.get("reply_target") or request.headers.get("X-Reply-Target") or panel_device_id or "").strip()

    messages = [{"role": "system", "content": _build_listen_context_system(entry, segment, current_time, duration), "__dynamic__": True}]
    messages.extend(_sanitize_recent_listen_messages(body.get("recent_messages")))
    messages.append({"role": "user", "content": text})
    chat_body = {
        "model": model,
        "stream": False,
        "window_id": window_id,
        "messages": messages,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": request.headers.get("User-Agent") or "SumiTalk Music Listen",
        "X-Force-Last4": str(request.headers.get("X-Force-Last4") or body.get("force_last4") or "1"),
        "X-Reply-Channel": "sumitalk",
        "X-Reply-Target": reply_target,
        "X-Window-Id": window_id,
        "X-Skip-Post-Archive-Dynamic-Memory": str(body.get("skip_post_archive_dynamic_memory") or "1"),
    }
    try:
        from routes.chat import chat_completions

        with current_app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=chat_body,
            headers=headers,
            environ_base={"REMOTE_ADDR": request.remote_addr or "127.0.0.1"},
        ):
            result = chat_completions()
            status_code, resp_json = _extract_chat_completion_result(result)
    except Exception as e:
        return jsonify({"ok": False, "error": f"调用聊天管道失败: {e}"}), 502

    if status_code >= 400:
        err = resp_json.get("error") or resp_json.get("message") or "upstream error"
        return jsonify({"ok": False, "error": str(err), "status_code": status_code, "resp": resp_json}), status_code

    du_reply = _extract_assistant_content(resp_json).strip()
    if not du_reply:
        return jsonify({"ok": False, "error": "上游没有返回内容", "resp": resp_json}), 502
    return jsonify({"ok": True, "du_reply": du_reply, "window_id": window_id, "entry_id": entry.get("id")})


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
