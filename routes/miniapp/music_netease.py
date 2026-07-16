from __future__ import annotations

from flask import jsonify, request

from services.music_melody_analyzer import MusicMelodyError, analyze_music_melody
from services.netease_music import (
    NeteaseMusicAuthError,
    NeteaseMusicDependencyError,
    NeteaseMusicError,
    check_login_qr,
    clear_login,
    create_login_qr,
    download_track_for_analysis,
    get_daily_recommendations,
    get_login_status,
    get_liked_track_ids,
    get_personal_fm,
    get_playlist_tracks,
    get_recent_tracks,
    get_track_lyrics,
    get_track_detail,
    get_track_source,
    list_playlists,
    list_toplists,
    search_tracks,
    set_track_liked,
    update_playlist_tracks,
)
from storage.music_melody_store import update_music_melody_source_by_id
from utils.log import get_logger


logger = get_logger(__name__)


def _int_arg(value: object, default: int, *, minimum: int = 0, maximum: int = 500) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bool_arg(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _error_response(error: Exception):
    if isinstance(error, NeteaseMusicDependencyError):
        status = 503
    elif isinstance(error, NeteaseMusicAuthError):
        status = 409
    elif isinstance(error, (NeteaseMusicError, MusicMelodyError)):
        status = 400
    else:
        logger.error("网易云一起听接口失败 error=%s", error, exc_info=True)
        status = 500
    return jsonify({"ok": False, "error": str(error)}), status


def register_routes(bp):
    @bp.route("/music/netease/status", methods=["GET"])
    def miniapp_music_netease_status():
        try:
            return jsonify({"ok": True, **get_login_status()})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/login/qr", methods=["POST"])
    def miniapp_music_netease_login_qr():
        try:
            return jsonify({"ok": True, **create_login_qr()})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/login/qr/<key>", methods=["GET"])
    def miniapp_music_netease_login_qr_check(key: str):
        try:
            return jsonify({"ok": True, **check_login_qr(key)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/logout", methods=["POST"])
    def miniapp_music_netease_logout():
        try:
            clear_login()
            return jsonify({"ok": True, "logged_in": False})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/search", methods=["GET"])
    def miniapp_music_netease_search():
        try:
            query = str(request.args.get("q") or request.args.get("query") or "").strip()
            limit = _int_arg(request.args.get("limit"), 30, minimum=1, maximum=50)
            offset = _int_arg(request.args.get("offset"), 0, minimum=0, maximum=100000)
            return jsonify({"ok": True, "items": search_tracks(query, limit=limit, offset=offset)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/recommendations/daily", methods=["GET"])
    def miniapp_music_netease_daily_recommendations():
        try:
            limit = _int_arg(request.args.get("limit"), 30, minimum=1, maximum=50)
            return jsonify({"ok": True, "items": get_daily_recommendations(limit=limit)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/personal-fm", methods=["GET"])
    def miniapp_music_netease_personal_fm():
        try:
            limit = _int_arg(request.args.get("limit"), 10, minimum=1, maximum=30)
            return jsonify({"ok": True, "items": get_personal_fm(limit=limit)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/playlists", methods=["GET"])
    def miniapp_music_netease_playlists():
        try:
            limit = _int_arg(request.args.get("limit"), 100, minimum=1, maximum=200)
            offset = _int_arg(request.args.get("offset"), 0, minimum=0, maximum=100000)
            return jsonify({"ok": True, "items": list_playlists(limit=limit, offset=offset)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/playlists/<playlist_id>/tracks", methods=["GET"])
    def miniapp_music_netease_playlist_tracks(playlist_id: str):
        try:
            limit = _int_arg(request.args.get("limit"), 300, minimum=1, maximum=500)
            offset = _int_arg(request.args.get("offset"), 0, minimum=0, maximum=100000)
            return jsonify({"ok": True, **get_playlist_tracks(playlist_id, limit=limit, offset=offset)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/playlists/<playlist_id>/tracks", methods=["POST"])
    def miniapp_music_netease_playlist_tracks_update(playlist_id: str):
        body = request.get_json(silent=True) if request.is_json else {}
        body = body if isinstance(body, dict) else {}
        try:
            track_ids = body.get("track_ids")
            if not isinstance(track_ids, list):
                raise NeteaseMusicError("track_ids 必须是数组")
            result = update_playlist_tracks(playlist_id, track_ids, str(body.get("operation") or ""))
            return jsonify({"ok": True, **result})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/likes", methods=["GET"])
    def miniapp_music_netease_likes():
        try:
            return jsonify({"ok": True, "ids": get_liked_track_ids()})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/tracks/<track_id>/like", methods=["POST"])
    def miniapp_music_netease_track_like(track_id: str):
        body = request.get_json(silent=True) if request.is_json else {}
        body = body if isinstance(body, dict) else {}
        try:
            if "liked" not in body:
                raise NeteaseMusicError("缺少 liked")
            return jsonify({"ok": True, **set_track_liked(track_id, _bool_arg(body.get("liked")))})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/recent", methods=["GET"])
    def miniapp_music_netease_recent():
        try:
            limit = _int_arg(request.args.get("limit"), 100, minimum=1, maximum=500)
            return jsonify({"ok": True, "items": get_recent_tracks(limit=limit)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/toplists", methods=["GET"])
    def miniapp_music_netease_toplists():
        try:
            return jsonify({"ok": True, "items": list_toplists()})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/toplists/<toplist_id>/tracks", methods=["GET"])
    def miniapp_music_netease_toplist_tracks(toplist_id: str):
        try:
            limit = _int_arg(request.args.get("limit"), 300, minimum=1, maximum=500)
            offset = _int_arg(request.args.get("offset"), 0, minimum=0, maximum=100000)
            return jsonify({"ok": True, **get_playlist_tracks(toplist_id, limit=limit, offset=offset)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/tracks/<track_id>/source", methods=["GET"])
    def miniapp_music_netease_track_source(track_id: str):
        """Resolve playback only. This route must never start or persist analysis."""
        try:
            level = str(request.args.get("level") or "standard").strip()
            return jsonify({"ok": True, "source": get_track_source(track_id, level=level)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/tracks/<track_id>", methods=["GET"])
    def miniapp_music_netease_track_detail(track_id: str):
        try:
            return jsonify({"ok": True, "track": get_track_detail(track_id)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/tracks/<track_id>/lyrics", methods=["GET"])
    def miniapp_music_netease_track_lyrics(track_id: str):
        try:
            return jsonify({"ok": True, "lyrics": get_track_lyrics(track_id)})
        except Exception as e:
            return _error_response(e)

    @bp.route("/music/netease/tracks/<track_id>/analyze", methods=["POST"])
    def miniapp_music_netease_track_analyze(track_id: str):
        """The only NetEase route that downloads audio and invokes the existing analyzer."""
        body = request.get_json(silent=True) if request.is_json else {}
        body = body if isinstance(body, dict) else {}
        try:
            prepared = download_track_for_analysis(
                track_id,
                level=str(body.get("level") or "lossless").strip(),
            )
            track = prepared["track"]
            lyrics = prepared.get("lyrics") if isinstance(prepared.get("lyrics"), dict) else {}
            result = analyze_music_melody(
                title=str(track.get("title") or f"网易云歌曲 {track_id}"),
                artist=str(track.get("artist") or ""),
                audio_bytes=prepared["audio_bytes"],
                filename=str(prepared.get("filename") or f"netease-{track_id}.audio"),
                mime_type=str(prepared.get("mime_type") or ""),
                force=_bool_arg(body.get("force")),
                model=str(body.get("model") or "").strip(),
                prompt_version=str(body.get("prompt_version") or "").strip(),
                duration_seconds=max(0.0, float(track.get("duration_ms") or 0) / 1000.0),
                lyrics_text=str(lyrics.get("lyric") or ""),
            )
            entry = result.get("entry") if isinstance(result.get("entry"), dict) else {}
            entry_id = str(entry.get("id") or "").strip()
            if entry_id:
                linked = update_music_melody_source_by_id(
                    entry_id,
                    source_provider="netease",
                    source_track_id=str(track.get("id") or track_id),
                    source_cover_url=str(track.get("cover_url") or ""),
                )
                if linked:
                    result["entry"] = linked
            return jsonify(
                {
                    **result,
                    "netease": {
                        "track": track,
                        "source": prepared.get("source") or {},
                        "lyrics_available": bool(lyrics.get("lyric")),
                    },
                }
            )
        except Exception as e:
            return _error_response(e)
