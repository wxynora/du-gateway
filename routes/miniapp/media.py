from __future__ import annotations

import base64
import logging
import time
from urllib.parse import quote
from uuid import uuid4

from flask import Response, jsonify, request

from config import R2_PUBLIC_URL, TELEGRAM_PROACTIVE_TARGET_USER_ID, VOICE_CALL_MAX_BYTES, VOICE_CALL_WINDOW_ID
from storage import r2_store
from services.html_preview_store import resolve_preview_base_url_for_http_request
from utils.time_aware import now_beijing_iso

logger = logging.getLogger(__name__)

TTS_EMOTION_VALUES = {"", "happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm", "fluent", "whisper"}
CHAT_MEDIA_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
CHAT_MEDIA_AUDIO_TYPES = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg"}
CHAT_MEDIA_DOCUMENT_TYPES = {"text/plain", "text/markdown", "text/x-markdown"}
CHAT_MEDIA_DOCUMENT_EXTS = {".txt", ".md", ".markdown"}
CHAT_MEDIA_IMAGE_MAX_BYTES = 12 * 1024 * 1024
CHAT_MEDIA_AUDIO_MAX_BYTES = max(1024, int(VOICE_CALL_MAX_BYTES or (12 * 1024 * 1024)))
CHAT_MEDIA_DOCUMENT_MAX_BYTES = 1024 * 1024
CHAT_MEDIA_DOCUMENT_MAX_CHARS = 60000


def _voice_call_default_config() -> dict:
    return {
        "displayName": "渡",
        "subtitle": "语音通话中",
        "avatarVersion": 0,
        "useAvatarImage": False,
        "theme": "night",
        "ttsEmotion": "",
    }


def _normalize_tts_emotion(value: object) -> str:
    emotion = str(value or "").strip().lower()
    return emotion if emotion in TTS_EMOTION_VALUES else ""


def _miniapp_voice_avatar_url(avatar_version: int) -> str:
    v = max(0, int(avatar_version or 0))
    if v > 0:
        return f"/miniapp-api/voice-avatar/{v}"
    return "/miniapp-api/voice-avatar"


def _chat_media_public_url(key: str) -> str:
    media_key = str(key or "").strip()
    public_base = (R2_PUBLIC_URL or "").strip().rstrip("/")
    if public_base:
        return f"{public_base}/{media_key.lstrip('/')}"
    base = resolve_preview_base_url_for_http_request(request.url_root or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/miniapp-api/chat-media/raw-public?key={quote(media_key, safe='/')}"


def _chat_media_attachment(row: dict, *, duration_ms: int = 0, transcript: str = "", text_preview: str = "") -> dict:
    key = str((row or {}).get("key") or "").strip()
    kind = str((row or {}).get("kind") or "").strip().lower()
    ctype = str((row or {}).get("contentType") or "").strip().lower()
    name = str((row or {}).get("name") or "").strip()
    item = {
        "id": key.rsplit("/", 1)[-1] if key else uuid4().hex,
        "kind": kind,
        "name": name,
        "mime": ctype,
        "remoteKey": key,
        "remoteUrl": _chat_media_public_url(key),
        "size": int((row or {}).get("size") or 0),
        "createdAt": str((row or {}).get("createdAt") or now_beijing_iso()),
    }
    if duration_ms > 0:
        item["durationMs"] = int(duration_ms)
    if transcript:
        item["transcript"] = transcript
    if text_preview:
        item["textPreview"] = text_preview
    return item


def _chat_media_filename_ext(filename: str) -> str:
    name = str(filename or "").strip().lower()
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1]


def _chat_media_kind_for_mime(mime_type: str, explicit_kind: str = "", filename: str = "") -> str:
    kind = str(explicit_kind or "").strip().lower()
    mt = str(mime_type or "").strip().lower()
    ext = _chat_media_filename_ext(filename)
    if kind == "document":
        return "document"
    if kind in {"image", "audio"}:
        return kind
    if mt in CHAT_MEDIA_AUDIO_TYPES or mt.startswith("audio/"):
        return "audio"
    if mt in CHAT_MEDIA_DOCUMENT_TYPES or ext in CHAT_MEDIA_DOCUMENT_EXTS:
        return "document"
    return "image"


def _chat_media_document_supported(mime_type: str, filename: str) -> bool:
    mt = str(mime_type or "").strip().lower()
    ext = _chat_media_filename_ext(filename)
    return mt in CHAT_MEDIA_DOCUMENT_TYPES or ext in CHAT_MEDIA_DOCUMENT_EXTS


def _decode_chat_text_document(content: bytes) -> str:
    text = (content or b"").decode("utf-8-sig", errors="replace").strip()
    if len(text) > CHAT_MEDIA_DOCUMENT_MAX_CHARS:
        return text[:CHAT_MEDIA_DOCUMENT_MAX_CHARS].rstrip() + f"\n\n[文档过长，已截断到前 {CHAT_MEDIA_DOCUMENT_MAX_CHARS} 字]"
    return text


def _resolve_voice_call_window_id(explicit_window_id: str = "") -> str:
    wid = str(explicit_window_id or "").strip()
    if wid:
        return wid
    tg_uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if tg_uid > 0:
        return f"tg_{tg_uid}"
    return (VOICE_CALL_WINDOW_ID or "miniapp_voice_call").strip() or "miniapp_voice_call"


def _sort_call_records(items: list[dict]) -> list[dict]:
    return sorted(items or [], key=lambda x: str(x.get("updated_at") or x.get("started_at") or ""), reverse=True)


def _call_record_summary(item: dict) -> dict:
    turns = item.get("turns") or []
    started_at = str(item.get("started_at") or "").strip()
    title = str(item.get("title") or "").strip()
    if not title:
        title = "语音通话"
    preview = ""
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("text") or "").strip()
        if text:
            preview = text[:48]
            break
    return {
        "id": str(item.get("id") or "").strip(),
        "mode": str(item.get("mode") or "voice"),
        "started_at": started_at,
        "updated_at": str(item.get("updated_at") or started_at).strip() or started_at,
        "title": title,
        "preview": preview,
        "turn_count": len(turns),
    }


def _append_call_record_turns(call_id: str, started_at: str, turns: list[dict], mode: str = "voice") -> bool:
    cid = str(call_id or "").strip()
    if not cid or not turns:
        return False
    items = r2_store.get_miniapp_call_records() or []
    now_ts = now_beijing_iso()
    found = None
    for item in items:
        if str(item.get("id") or "").strip() == cid:
            found = item
            break
    if found is None:
        found = {
            "id": cid,
            "mode": mode or "voice",
            "started_at": started_at or now_ts,
            "updated_at": now_ts,
            "title": "语音通话",
            "turns": [],
        }
        items.append(found)
    found["updated_at"] = now_ts
    found.setdefault("turns", [])
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("text") or "").strip()
        role = str(turn.get("role") or "").strip().lower()
        if not text or role not in ("user", "assistant"):
            continue
        found["turns"].append(
            {
                "id": str(uuid4()),
                "role": role,
                "text": text,
                "kind": str(turn.get("kind") or "voice").strip() or "voice",
                "timestamp": str(turn.get("timestamp") or now_ts).strip() or now_ts,
            }
        )
    if found.get("turns"):
        first_text = str((found.get("turns") or [{}])[0].get("text") or "").strip()
        found["title"] = first_text[:24] if first_text else "语音通话"
    items = _sort_call_records(items)
    return r2_store.save_miniapp_call_records(items)


def register_routes(bp) -> None:
    @bp.route("/background-config", methods=["GET"])
    def miniapp_get_background_config():
        data = r2_store.get_miniapp_bg_config() or {}
        return jsonify(
            {
                "ok": True,
                "config": {
                    "preset": (data.get("preset") or "cream"),
                    "useImage": bool(data.get("useImage")),
                    "imageVersion": int(data.get("imageVersion") or 0),
                    "dim": int(data.get("dim") or 20),
                },
            }
        )

    @bp.route("/background-config", methods=["PUT"])
    def miniapp_put_background_config():
        data = request.get_json(silent=True) or {}
        preset = (data.get("preset") or "cream").strip()
        if preset not in ("cream", "grid", "soft"):
            preset = "cream"
        dim = int(data.get("dim") or 20)
        dim = max(0, min(70, dim))
        use_image = bool(data.get("useImage"))
        image_version = int(data.get("imageVersion") or 0)
        # 防止客户端携带旧 draft 覆盖新图版本号：配置保存时版本号只允许前进不回退。
        current = r2_store.get_miniapp_bg_config() or {}
        current_ver = int(current.get("imageVersion") or 0)
        payload = {
            "preset": preset,
            "useImage": use_image,
            "imageVersion": max(current_ver, max(0, image_version)),
            "dim": dim,
        }
        ok = r2_store.save_miniapp_bg_config(payload)
        return jsonify({"ok": ok, "config": payload})

    @bp.route("/background-image", methods=["POST"])
    def miniapp_upload_background_image():
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "缺少 file"}), 400
        ctype = (f.mimetype or "").strip().lower()
        if ctype not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            return jsonify({"ok": False, "error": "仅支持 jpg/png/webp/gif"}), 400
        content = f.read()
        if not content:
            return jsonify({"ok": False, "error": "文件为空"}), 400
        if len(content) > 8 * 1024 * 1024:
            return jsonify({"ok": False, "error": "图片过大（最大 8MB）"}), 400
        conf = r2_store.get_miniapp_bg_config() or {}
        # 用毫秒时间戳，且保证严格递增，避免同一秒内二次上传命中同一个版本号导致前端继续读旧缓存。
        old_ver = int(conf.get("imageVersion") or 0)
        new_ver = int(time.time() * 1000)
        if new_ver <= old_ver:
            new_ver = old_ver + 1

        # 同时写“最新别名键 + 版本化键”，规避顽固缓存回旧图问题
        ok = r2_store.save_miniapp_bg_image(content, ctype, image_version=new_ver)
        if not ok:
            return jsonify({"ok": False, "error": "保存失败"}), 500
        conf["imageVersion"] = new_ver
        conf["useImage"] = True
        conf["dim"] = max(0, min(70, int(conf.get("dim") or 20)))
        conf["preset"] = conf.get("preset") or "cream"
        r2_store.save_miniapp_bg_config(conf)
        return jsonify({"ok": True, "imageVersion": int(conf["imageVersion"])})

    @bp.route("/background-image", methods=["GET"])
    def miniapp_get_background_image():
        data, ctype = r2_store.get_miniapp_bg_image()
        if not data:
            return jsonify({"ok": False, "error": "暂无背景图"}), 404
        # 背景图支持频繁替换：这里禁用强缓存，实际刷新仍由 imageVersion 控制兜底。
        return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})

    @bp.route("/background-image/<int:image_version>", methods=["GET"])
    def miniapp_get_background_image_versioned(image_version: int):
        """
        版本化路径读取背景图：
        - 目的：避免 WebView/代理对同一路径缓存过于激进导致“明明上传了仍显示旧图”。
        - 实际图片仍取当前存储，版本号用于强制路径变化。
        """
        data, ctype = r2_store.get_miniapp_bg_image(image_version=image_version)
        if not data:
            return jsonify({"ok": False, "error": "暂无背景图"}), 404
        return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})

    @bp.route("/voice-config", methods=["GET"])
    def miniapp_get_voice_config():
        raw = r2_store.get_miniapp_voice_config() or {}
        merged = _voice_call_default_config()
        merged.update({k: v for k, v in raw.items() if v is not None})
        avatar_version = int(merged.get("avatarVersion") or 0)
        merged["avatarVersion"] = avatar_version
        merged["useAvatarImage"] = bool(merged.get("useAvatarImage"))
        if not merged["useAvatarImage"]:
            data, _ = r2_store.get_miniapp_voice_avatar()
            if data:
                merged["useAvatarImage"] = True
        merged["avatarUrl"] = _miniapp_voice_avatar_url(avatar_version) if avatar_version > 0 and merged["useAvatarImage"] else ""
        if merged["useAvatarImage"] and not merged["avatarUrl"]:
            merged["avatarUrl"] = "/miniapp-api/voice-avatar"
        return jsonify({"ok": True, "config": merged})

    @bp.route("/voice-config", methods=["PUT"])
    def miniapp_put_voice_config():
        data = request.get_json(silent=True) or {}
        current = r2_store.get_miniapp_voice_config() or {}
        payload = _voice_call_default_config()
        payload.update({k: v for k, v in current.items() if v is not None})
        display_name = str(data.get("displayName") or payload.get("displayName") or "渡").strip()[:24] or "渡"
        subtitle = str(data.get("subtitle") or payload.get("subtitle") or "语音通话中").strip()[:40] or "语音通话中"
        theme = str(data.get("theme") or payload.get("theme") or "night").strip()[:16] or "night"
        if "ttsEmotion" in data:
            tts_emotion = _normalize_tts_emotion(data.get("ttsEmotion"))
        else:
            tts_emotion = _normalize_tts_emotion(payload.get("ttsEmotion"))
        # 防止客户端携带旧 draft 覆盖新头像版本号：版本号只允许前进不回退。
        current_ver = int(payload.get("avatarVersion") or 0)
        avatar_version = max(current_ver, max(0, int(data.get("avatarVersion") or 0)))
        payload.update(
            {
                "displayName": display_name,
                "subtitle": subtitle,
                "theme": theme,
                "ttsEmotion": tts_emotion,
                "avatarVersion": avatar_version,
                "useAvatarImage": bool(data.get("useAvatarImage", payload.get("useAvatarImage"))),
            }
        )
        ok = r2_store.save_miniapp_voice_config(payload)
        payload["avatarUrl"] = _miniapp_voice_avatar_url(avatar_version) if avatar_version > 0 and payload["useAvatarImage"] else ""
        return jsonify({"ok": ok, "config": payload})

    @bp.route("/voice-avatar", methods=["POST"])
    def miniapp_upload_voice_avatar():
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "缺少 file"}), 400
        ctype = (f.mimetype or "").strip().lower()
        if ctype not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            return jsonify({"ok": False, "error": "仅支持 jpg/png/webp/gif"}), 400
        content = f.read()
        if not content:
            return jsonify({"ok": False, "error": "文件为空"}), 400
        if len(content) > 8 * 1024 * 1024:
            return jsonify({"ok": False, "error": "头像过大（最大 8MB）"}), 400
        conf = r2_store.get_miniapp_voice_config() or _voice_call_default_config()
        old_ver = int(conf.get("avatarVersion") or 0)
        new_ver = int(time.time() * 1000)
        if new_ver <= old_ver:
            new_ver = old_ver + 1
        ok = r2_store.save_miniapp_voice_avatar(content, ctype, image_version=new_ver)
        if not ok:
            return jsonify({"ok": False, "error": "头像保存失败"}), 500
        conf["avatarVersion"] = new_ver
        conf["useAvatarImage"] = True
        conf_ok = r2_store.save_miniapp_voice_config(conf)
        if not conf_ok:
            return jsonify({"ok": False, "error": "头像配置保存失败"}), 500
        return jsonify({"ok": True, "avatarVersion": new_ver, "avatarUrl": _miniapp_voice_avatar_url(new_ver)})

    @bp.route("/voice-avatar", methods=["GET"])
    def miniapp_get_voice_avatar():
        data, ctype = r2_store.get_miniapp_voice_avatar()
        if not data:
            return jsonify({"ok": False, "error": "暂无头像"}), 404
        return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})

    @bp.route("/voice-avatar/<int:image_version>", methods=["GET"])
    def miniapp_get_voice_avatar_versioned(image_version: int):
        data, ctype = r2_store.get_miniapp_voice_avatar(image_version=image_version)
        if not data:
            return jsonify({"ok": False, "error": "暂无头像"}), 404
        return Response(data, mimetype=ctype, headers={"Cache-Control": "no-store, max-age=0"})

    @bp.route("/voice-call", methods=["POST"])
    def miniapp_voice_call():
        f = request.files.get("audio")
        if not f:
            return jsonify({"ok": False, "error": "缺少 audio"}), 400
        mime_type = (f.mimetype or request.form.get("mime_type") or "application/octet-stream").strip().lower()
        if mime_type not in ("audio/webm", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg"):
            return jsonify({"ok": False, "error": f"暂不支持的音频格式：{mime_type or 'unknown'}"}), 400
        audio_bytes = f.read()
        if not audio_bytes:
            return jsonify({"ok": False, "error": "音频为空"}), 400
        if len(audio_bytes) > max(1024, int(VOICE_CALL_MAX_BYTES or 0)):
            return jsonify({"ok": False, "error": "音频太大了，缩短一点再试"}), 400

        filename = (f.filename or "voice.webm").strip() or "voice.webm"
        window_id = _resolve_voice_call_window_id(request.form.get("window_id") or "")
        call_id = (request.form.get("call_id") or "").strip() or str(uuid4())
        call_started_at = (request.form.get("call_started_at") or "").strip() or now_beijing_iso()
        user_text_override = (request.form.get("user_text_override") or "").strip()
        try:
            from services.voice_call_pipeline import run_voice_call
        except Exception as e:
            logger.warning("voice-call 依赖加载失败 err=%s", e)
            return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500

        payload, status = run_voice_call(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            filename=filename,
            window_id=window_id,
            user_text_override=user_text_override,
        )
        if status >= 400:
            return jsonify(payload), status
        _append_call_record_turns(
            call_id=call_id,
            started_at=call_started_at,
            turns=[
                {"role": "user", "text": payload.get("user_text"), "kind": "voice", "timestamp": now_beijing_iso()},
                {"role": "assistant", "text": payload.get("reply_text"), "kind": "voice", "timestamp": now_beijing_iso()},
            ],
            mode="voice",
        )
        payload["call_id"] = call_id
        payload["call_started_at"] = call_started_at
        return jsonify(payload), status

    @bp.route("/voice-call-preview", methods=["POST"])
    def miniapp_voice_call_preview():
        f = request.files.get("audio")
        if not f:
            return jsonify({"ok": False, "error": "缺少 audio"}), 400
        mime_type = (f.mimetype or request.form.get("mime_type") or "application/octet-stream").strip().lower()
        if mime_type not in ("audio/webm", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg"):
            return jsonify({"ok": False, "error": f"暂不支持的音频格式：{mime_type or 'unknown'}"}), 400
        audio_bytes = f.read()
        if not audio_bytes:
            return jsonify({"ok": False, "error": "音频为空"}), 400
        filename = (f.filename or "voice.webm").strip() or "voice.webm"
        try:
            from services.stt import transcribe_speech
        except Exception as e:
            logger.warning("voice-call-preview 依赖加载失败 err=%s", e)
            return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500
        result = transcribe_speech(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename) or {}
        return jsonify(
            {
                "ok": True,
                "text": str(result.get("text") or ""),
                "audio_observations": str(result.get("audio_observations") or ""),
                "stt_provider": str(result.get("provider") or ""),
            }
        )

    @bp.route("/tts-preview", methods=["POST"])
    def miniapp_tts_preview():
        body = request.get_json(silent=True) or {}
        text = str(body.get("text") or "").strip()
        audio_format = str(body.get("audio_format") or "mp3").strip().lower() or "mp3"
        if not text:
            return jsonify({"ok": False, "error": "缺少 text"}), 400
        if audio_format not in ("mp3", "wav"):
            return jsonify({"ok": False, "error": f"暂不支持的 audio_format：{audio_format}"}), 400
        try:
            from services.minimax_tts import tts_to_audio_bytes
        except Exception as e:
            logger.warning("tts-preview 依赖加载失败 err=%s", e)
            return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500
        audio_bytes = tts_to_audio_bytes(text, audio_format=audio_format)
        if not audio_bytes:
            return jsonify({"ok": False, "error": "语音生成失败"}), 502
        call_id = str(body.get("call_id") or body.get("callId") or "").strip()
        if call_id:
            try:
                _append_call_record_turns(
                    call_id,
                    str(body.get("call_started_at") or body.get("callStartedAt") or now_beijing_iso()),
                    [{"role": "assistant", "text": text, "kind": "voice_opening"}],
                    mode="voice",
                )
            except Exception:
                logger.warning("tts-preview call record append failed call_id=%s", call_id, exc_info=True)
        return jsonify(
            {
                "ok": True,
                "audio_b64": base64.b64encode(audio_bytes).decode("ascii"),
                "audio_format": audio_format,
            }
        )

    @bp.route("/chat-media/upload", methods=["POST"])
    def miniapp_chat_media_upload():
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "缺少 file"}), 400
        mime_type = (f.mimetype or request.form.get("mime_type") or "application/octet-stream").strip().lower()
        filename = (f.filename or "chat-media").strip() or "chat-media"
        kind = _chat_media_kind_for_mime(mime_type, request.form.get("kind") or "", filename)
        if kind == "audio":
            allowed = CHAT_MEDIA_AUDIO_TYPES
            max_bytes = CHAT_MEDIA_AUDIO_MAX_BYTES
            supported = mime_type in allowed
        elif kind == "document":
            allowed = CHAT_MEDIA_DOCUMENT_TYPES
            max_bytes = CHAT_MEDIA_DOCUMENT_MAX_BYTES
            supported = _chat_media_document_supported(mime_type, filename)
        else:
            allowed = CHAT_MEDIA_IMAGE_TYPES
            max_bytes = CHAT_MEDIA_IMAGE_MAX_BYTES
            supported = mime_type in allowed
        if not supported:
            return jsonify({"ok": False, "error": f"暂不支持的文件格式：{mime_type or 'unknown'}"}), 400
        content = f.read()
        if not content:
            return jsonify({"ok": False, "error": "文件为空"}), 400
        if len(content) > max_bytes:
            return jsonify({"ok": False, "error": "文件太大了，换小一点再试"}), 400
        text_preview = ""
        if kind == "document":
            text_preview = _decode_chat_text_document(content)
            if not text_preview:
                return jsonify({"ok": False, "error": "文档内容为空"}), 400
        row = r2_store.upload_sumitalk_chat_media_file(kind, filename, content, mime_type)
        if not row:
            return jsonify({"ok": False, "error": "上传失败"}), 500
        attachment = _chat_media_attachment(row, text_preview=text_preview)
        return jsonify({"ok": True, "media": attachment, "attachment": attachment})

    @bp.route("/chat-media/transcribe", methods=["POST"])
    def miniapp_chat_media_transcribe():
        f = request.files.get("audio") or request.files.get("file")
        if not f:
            logger.warning("[SumiTalk] chat_media_transcribe_reject reason=missing_audio")
            return jsonify({"ok": False, "error": "缺少 audio"}), 400
        mime_type = (f.mimetype or request.form.get("mime_type") or "application/octet-stream").strip().lower()
        if mime_type not in CHAT_MEDIA_AUDIO_TYPES:
            logger.warning("[SumiTalk] chat_media_transcribe_reject reason=unsupported_mime mime=%s", mime_type or "unknown")
            return jsonify({"ok": False, "error": f"暂不支持的音频格式：{mime_type or 'unknown'}"}), 400
        audio_bytes = f.read()
        if not audio_bytes:
            logger.warning("[SumiTalk] chat_media_transcribe_reject reason=empty_audio mime=%s", mime_type)
            return jsonify({"ok": False, "error": "音频为空"}), 400
        if len(audio_bytes) > CHAT_MEDIA_AUDIO_MAX_BYTES:
            logger.warning("[SumiTalk] chat_media_transcribe_reject reason=too_large mime=%s bytes=%s max_bytes=%s", mime_type, len(audio_bytes), CHAT_MEDIA_AUDIO_MAX_BYTES)
            return jsonify({"ok": False, "error": "语音太长了，缩短一点再试"}), 400
        filename = (f.filename or "voice.webm").strip() or "voice.webm"
        logger.info(
            "[SumiTalk] chat_media_transcribe_start mime=%s bytes=%s filename=%s",
            mime_type,
            len(audio_bytes),
            filename[:120],
        )
        stt_started = time.time()
        try:
            from services.stt import transcribe_speech
        except Exception as e:
            logger.warning("[SumiTalk] chat_media_transcribe_error stage=load_stt_dependency err=%s", e)
            return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500
        try:
            result = transcribe_speech(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename) or {}
        except Exception as e:
            logger.warning(
                "[SumiTalk] chat_media_transcribe_error stage=stt_call mime=%s bytes=%s elapsed_ms=%s err=%s",
                mime_type,
                len(audio_bytes),
                int((time.time() - stt_started) * 1000),
                e,
                exc_info=True,
            )
            return jsonify({"ok": False, "error": "语音转写失败"}), 500
        text = str(result.get("text") or "").strip()
        row = r2_store.upload_sumitalk_chat_media_file("audio", filename, audio_bytes, mime_type)
        if not row:
            logger.warning(
                "[SumiTalk] chat_media_transcribe_error stage=save_audio mime=%s bytes=%s elapsed_ms=%s text_len=%s",
                mime_type,
                len(audio_bytes),
                int((time.time() - stt_started) * 1000),
                len(text),
            )
            return jsonify({"ok": False, "error": "语音保存失败"}), 500
        attachment = _chat_media_attachment(row, transcript=text)
        logger.info(
            "[SumiTalk] chat_media_transcribe_ok mime=%s bytes=%s elapsed_ms=%s text_len=%s provider=%s saved=%s",
            mime_type,
            len(audio_bytes),
            int((time.time() - stt_started) * 1000),
            len(text),
            str(result.get("provider") or "")[:80],
            bool(row),
        )
        return jsonify(
            {
                "ok": True,
                "text": text,
                "audio_observations": str(result.get("audio_observations") or ""),
                "stt_provider": str(result.get("provider") or ""),
                "media": attachment,
                "attachment": attachment,
            }
        )

    @bp.route("/chat-media/tts", methods=["POST"])
    def miniapp_chat_media_tts():
        body = request.get_json(silent=True) or {}
        text = str(body.get("text") or "").strip()
        audio_format = str(body.get("audio_format") or "mp3").strip().lower() or "mp3"
        if not text:
            logger.warning("[SumiTalk] chat_media_tts_reject reason=empty_text")
            return jsonify({"ok": False, "error": "缺少 text"}), 400
        if audio_format not in ("mp3", "wav"):
            logger.warning("[SumiTalk] chat_media_tts_reject reason=unsupported_format format=%s", audio_format)
            return jsonify({"ok": False, "error": f"暂不支持的 audio_format：{audio_format}"}), 400
        logger.info("[SumiTalk] chat_media_tts_start text_len=%s format=%s", len(text), audio_format)
        tts_started = time.time()
        try:
            from services.minimax_tts import tts_to_audio_bytes
        except Exception as e:
            logger.warning("[SumiTalk] chat_media_tts_error stage=load_tts_dependency err=%s", e)
            return jsonify({"ok": False, "error": "语音服务初始化失败"}), 500
        audio_bytes = tts_to_audio_bytes(text, audio_format=audio_format)
        if not audio_bytes:
            logger.warning(
                "[SumiTalk] chat_media_tts_error stage=tts_call text_len=%s elapsed_ms=%s",
                len(text),
                int((time.time() - tts_started) * 1000),
            )
            return jsonify({"ok": False, "error": "语音生成失败"}), 502
        mime_type = "audio/wav" if audio_format == "wav" else "audio/mpeg"
        row = r2_store.upload_sumitalk_chat_media_file("audio", f"du-reply.{audio_format}", audio_bytes, mime_type)
        if not row:
            logger.warning(
                "[SumiTalk] chat_media_tts_error stage=save_audio bytes=%s elapsed_ms=%s",
                len(audio_bytes),
                int((time.time() - tts_started) * 1000),
            )
            return jsonify({"ok": False, "error": "语音保存失败"}), 500
        attachment = _chat_media_attachment(row, transcript=text)
        logger.info(
            "[SumiTalk] chat_media_tts_ok bytes=%s elapsed_ms=%s mime=%s",
            len(audio_bytes),
            int((time.time() - tts_started) * 1000),
            mime_type,
        )
        return jsonify({"ok": True, "media": attachment, "attachment": attachment})

    @bp.route("/chat-media/raw-public", methods=["GET"])
    def miniapp_chat_media_raw_public():
        key = (request.args.get("key") or "").strip()
        data, ctype = r2_store.get_sumitalk_chat_media_file(key)
        if not data:
            return jsonify({"ok": False, "error": "未找到"}), 404
        return Response(data, mimetype=ctype or "application/octet-stream", headers={"Cache-Control": "public, max-age=86400"})

    @bp.route("/call-records", methods=["GET"])
    def miniapp_get_call_records():
        items = _sort_call_records(r2_store.get_miniapp_call_records() or [])
        rows = [_call_record_summary(item) for item in items]
        return jsonify({"ok": True, "items": rows})

    @bp.route("/call-records/<string:call_id>", methods=["GET"])
    def miniapp_get_call_record_detail(call_id: str):
        cid = str(call_id or "").strip()
        if not cid:
            return jsonify({"ok": False, "error": "缺少通话 id"}), 400
        items = r2_store.get_miniapp_call_records() or []
        for item in items:
            if str(item.get("id") or "").strip() != cid:
                continue
            return jsonify(
                {
                    "ok": True,
                    "item": {
                        **_call_record_summary(item),
                        "turns": item.get("turns") or [],
                    },
                }
            )
        return jsonify({"ok": False, "error": "找不到这条通话记录"}), 404

    @bp.route("/call-records/<string:call_id>", methods=["DELETE"])
    def miniapp_delete_call_record(call_id: str):
        cid = str(call_id or "").strip()
        if not cid:
            return jsonify({"ok": False, "error": "缺少通话 id"}), 400
        ok = r2_store.delete_miniapp_call_record(cid)
        if not ok:
            return jsonify({"ok": False, "error": "删除失败或记录不存在"}), 404
        return jsonify({"ok": True, "id": cid})
