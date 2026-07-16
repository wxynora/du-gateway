from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from config import DATA_DIR, MUSIC_AUDIO_MAX_BYTES
from utils.log import get_logger


logger = get_logger(__name__)

NETEASE_SESSION_FILE = DATA_DIR / "netease_music_session.json"
NETEASE_SESSION_LOCK_FILE = DATA_DIR / ".netease_music_session.lock"
NETEASE_QR_TTL_SECONDS = 300
NETEASE_AUDIO_LEVELS = {"standard", "exhigh", "lossless", "hires"}
NETEASE_AUDIO_HOST_SUFFIXES = ("music.126.net", "music.163.com")
_STATE_THREAD_LOCK = threading.RLock()
_TRACK_ID_RE = re.compile(r"^[1-9]\d{0,19}$")
_QR_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{6,240}$")


class NeteaseMusicError(Exception):
    pass


class NeteaseMusicDependencyError(NeteaseMusicError):
    pass


class NeteaseMusicAuthError(NeteaseMusicError):
    pass


def _pyncm_modules() -> dict[str, Any]:
    try:
        from pyncm import DumpSessionAsString, LoadSessionFromString, Session, WriteLoginInfo
        from pyncm.apis import WeapiCryptoRequest, cloudsearch, login, playlist, track, user
    except Exception as e:
        raise NeteaseMusicDependencyError("PyNCM 未安装，网易云曲库暂不可用") from e
    @WeapiCryptoRequest
    def get_user_like_list(user_id):
        return "/weapi/song/like/get", {"uid": str(user_id)}

    @WeapiCryptoRequest
    def get_user_play_record(user_id, record_type=0):
        return "/weapi/v1/play/record", {
            "uid": str(user_id),
            "type": str(record_type),
            "limit": "1000",
            "offset": "0",
            "total": "true",
        }

    @WeapiCryptoRequest
    def get_daily_recommendations():
        return "/api/v3/discovery/recommend/songs", {}

    @WeapiCryptoRequest
    def get_personal_fm(limit=3):
        return "/api/v1/radio/get", {"limit": str(limit)}

    return {
        "Session": Session,
        "DumpSessionAsString": DumpSessionAsString,
        "LoadSessionFromString": LoadSessionFromString,
        "WriteLoginInfo": WriteLoginInfo,
        "cloudsearch": cloudsearch,
        "login": login,
        "playlist": playlist,
        "track": track,
        "user": user,
        "get_user_like_list": get_user_like_list,
        "get_user_play_record": get_user_play_record,
        "get_daily_recommendations": get_daily_recommendations,
        "get_personal_fm": get_personal_fm,
    }


def _with_default_timeout(session: Any, seconds: int = 25) -> Any:
    if getattr(session, "_sumitalk_default_timeout", False):
        return session
    original_request = session.request

    def request_with_timeout(method, url, *args, **kwargs):
        kwargs.setdefault("timeout", seconds)
        return original_request(method, url, *args, **kwargs)

    session.request = request_with_timeout
    session._sumitalk_default_timeout = True
    return session


@contextmanager
def _state_guard():
    NETEASE_SESSION_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _STATE_THREAD_LOCK:
        with open(NETEASE_SESSION_LOCK_FILE, "a+", encoding="utf-8") as lock_file:
            try:
                os.chmod(NETEASE_SESSION_LOCK_FILE, 0o600)
            except OSError:
                pass
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _empty_state() -> dict:
    return {"version": 1, "active_session": "", "active_profile": {}, "pending": {}}


def _read_state_unlocked() -> dict:
    try:
        raw = json.loads(NETEASE_SESSION_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_state()
    except Exception as e:
        logger.warning("读取网易云登录态失败 error=%s", e)
        return _empty_state()
    if not isinstance(raw, dict):
        return _empty_state()
    state = _empty_state()
    state["active_session"] = str(raw.get("active_session") or "")
    state["active_profile"] = raw.get("active_profile") if isinstance(raw.get("active_profile"), dict) else {}
    state["pending"] = raw.get("pending") if isinstance(raw.get("pending"), dict) else {}
    return state


def _write_state_unlocked(state: dict) -> None:
    NETEASE_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".netease_music_session.",
        suffix=".tmp",
        dir=str(NETEASE_SESSION_FILE.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, NETEASE_SESSION_FILE)
        os.chmod(NETEASE_SESSION_FILE, 0o600)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _prune_pending(state: dict, now: float | None = None) -> None:
    current = float(now if now is not None else time.time())
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
    state["pending"] = {
        str(key): value
        for key, value in pending.items()
        if isinstance(value, dict) and float(value.get("expires_at") or 0) > current
    }


def _profile_from_status(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else data.get("profile") or {}
    account = payload.get("account") if isinstance(payload.get("account"), dict) else data.get("account") or {}
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(account, dict):
        account = {}
    uid = profile.get("userId") or account.get("id") or account.get("userId") or 0
    return {
        "user_id": str(uid or ""),
        "nickname": str(profile.get("nickname") or ""),
        "avatar_url": str(profile.get("avatarUrl") or ""),
        "vip_type": int(profile.get("vipType") or account.get("vipType") or 0),
    }


def create_login_qr() -> dict:
    modules = _pyncm_modules()
    session = _with_default_timeout(modules["Session"]())
    payload = modules["login"].LoginQrcodeUnikey(session=session)
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}
    key = str((payload or {}).get("unikey") or data.get("unikey") or "").strip() if isinstance(payload, dict) else ""
    if not _QR_KEY_RE.fullmatch(key):
        raise NeteaseMusicError("网易云没有返回有效二维码令牌")
    qr_url = str(modules["login"].GetLoginQRCodeUrl(key, session=session) or "").strip()
    if not qr_url:
        raise NeteaseMusicError("网易云没有返回二维码地址")
    now = time.time()
    with _state_guard():
        state = _read_state_unlocked()
        _prune_pending(state, now)
        state["pending"][key] = {
            "session": modules["DumpSessionAsString"](session),
            "created_at": now,
            "expires_at": now + NETEASE_QR_TTL_SECONDS,
        }
        _write_state_unlocked(state)
    return {"key": key, "qr_url": qr_url, "expires_in": NETEASE_QR_TTL_SECONDS}


def check_login_qr(key: str) -> dict:
    clean_key = str(key or "").strip()
    if not _QR_KEY_RE.fullmatch(clean_key):
        raise NeteaseMusicError("二维码令牌无效")
    modules = _pyncm_modules()
    now = time.time()
    with _state_guard():
        state = _read_state_unlocked()
        _prune_pending(state, now)
        pending = state.get("pending", {}).get(clean_key)
        if not isinstance(pending, dict) or not pending.get("session"):
            _write_state_unlocked(state)
            raise NeteaseMusicError("二维码已过期，请重新获取")
        session_dump = str(pending["session"])
    session = _with_default_timeout(modules["LoadSessionFromString"](session_dump))
    result = modules["login"].LoginQrcodeCheck(clean_key, session=session)
    if not isinstance(result, dict):
        raise NeteaseMusicError("网易云返回了无效登录状态")
    code = int(result.get("code") or 0)
    message = str(result.get("message") or "")
    if code == 803:
        status = modules["login"].GetCurrentLoginStatus(session=session)
        if not isinstance(status, dict) or int(status.get("code") or 0) != 200:
            raise NeteaseMusicError("扫码成功，但读取网易云账号失败")
        modules["WriteLoginInfo"](status, session)
        profile = _profile_from_status(status)
        if not profile.get("user_id"):
            raise NeteaseMusicError("扫码成功，但网易云账号缺少用户 ID")
    else:
        profile = {}
    with _state_guard():
        state = _read_state_unlocked()
        _prune_pending(state, now)
        if code == 803:
            state["active_session"] = modules["DumpSessionAsString"](session)
            state["active_profile"] = profile
            state["pending"].pop(clean_key, None)
            _write_state_unlocked(state)
            return {"code": code, "message": message, "logged_in": True, "profile": profile}
        current_pending = state.get("pending", {}).get(clean_key)
        if isinstance(current_pending, dict):
            current_pending["session"] = modules["DumpSessionAsString"](session)
        if code in {800, 8821} or not isinstance(current_pending, dict):
            state["pending"].pop(clean_key, None)
        _write_state_unlocked(state)
        return {"code": code, "message": message, "logged_in": False}


def get_login_status() -> dict:
    with _state_guard():
        state = _read_state_unlocked()
    profile = state.get("active_profile") if isinstance(state.get("active_profile"), dict) else {}
    if not state.get("active_session") or not profile.get("user_id"):
        return {"logged_in": False, "profile": {}}

    session, cached_profile, modules = _active_session()
    try:
        remote_status = modules["login"].GetCurrentLoginStatus(session=session)
    except Exception as e:
        raise NeteaseMusicError(f"网易云登录状态校验失败: {e}") from e
    remote_profile = _profile_from_status(remote_status) if isinstance(remote_status, dict) else {}
    if not isinstance(remote_status, dict) or int(remote_status.get("code") or 0) != 200 or not remote_profile.get("user_id"):
        clear_login()
        return {"logged_in": False, "profile": {}}

    modules["WriteLoginInfo"](remote_status, session)
    with _state_guard():
        latest = _read_state_unlocked()
        latest_profile = latest.get("active_profile") if isinstance(latest.get("active_profile"), dict) else {}
        if str(latest_profile.get("user_id") or "") == str(cached_profile.get("user_id") or ""):
            latest["active_session"] = modules["DumpSessionAsString"](session)
            latest["active_profile"] = remote_profile
            _write_state_unlocked(latest)
    return {"logged_in": True, "profile": remote_profile}


def clear_login() -> None:
    with _state_guard():
        state = _read_state_unlocked()
        state["active_session"] = ""
        state["active_profile"] = {}
        state["pending"] = {}
        _write_state_unlocked(state)


def _active_session() -> tuple[Any, dict, dict[str, Any]]:
    modules = _pyncm_modules()
    with _state_guard():
        state = _read_state_unlocked()
    session_dump = str(state.get("active_session") or "")
    profile = state.get("active_profile") if isinstance(state.get("active_profile"), dict) else {}
    if not session_dump or not profile.get("user_id"):
        raise NeteaseMusicAuthError("网易云尚未登录")
    try:
        session = _with_default_timeout(modules["LoadSessionFromString"](session_dump))
    except Exception as e:
        raise NeteaseMusicAuthError("网易云登录态已损坏，请重新扫码") from e
    return session, profile, modules


def _track_id(value: object) -> str:
    clean = str(value or "").strip()
    if not _TRACK_ID_RE.fullmatch(clean):
        raise NeteaseMusicError("网易云歌曲 ID 无效")
    return clean


def _level(value: object) -> str:
    clean = str(value or "standard").strip().lower() or "standard"
    if clean not in NETEASE_AUDIO_LEVELS:
        raise NeteaseMusicError("音质只能是 standard/exhigh/lossless/hires")
    return clean


def _map_track(raw: dict) -> dict:
    artists = raw.get("ar") if isinstance(raw.get("ar"), list) else raw.get("artists") or []
    album = raw.get("al") if isinstance(raw.get("al"), dict) else raw.get("album") or {}
    return {
        "id": str(raw.get("id") or ""),
        "title": str(raw.get("name") or ""),
        "artist": " / ".join(str(item.get("name") or "") for item in artists if isinstance(item, dict) and item.get("name")),
        "album": str(album.get("name") or "") if isinstance(album, dict) else "",
        "cover_url": str(album.get("picUrl") or "") if isinstance(album, dict) else "",
        "duration_ms": int(raw.get("dt") or raw.get("duration") or 0),
        "aliases": [str(item) for item in (raw.get("alia") or raw.get("alias") or []) if str(item).strip()],
        "fee": int(raw.get("fee") or 0),
    }


def _map_playlist(raw: dict, user_id: str = "") -> dict:
    creator = raw.get("creator") if isinstance(raw.get("creator"), dict) else {}
    creator_id = str(creator.get("userId") or "")
    return {
        "id": str(raw.get("id") or ""),
        "name": str(raw.get("name") or ""),
        "cover_url": str(raw.get("coverImgUrl") or ""),
        "track_count": int(raw.get("trackCount") or 0),
        "creator_id": creator_id,
        "creator_name": str(creator.get("nickname") or ""),
        "mine": bool(user_id and creator_id == str(user_id)),
    }


def _map_toplist(raw: dict) -> dict:
    return {
        "id": str(raw.get("id") or ""),
        "name": str(raw.get("name") or ""),
        "cover_url": str(raw.get("coverImgUrl") or raw.get("coverUrl") or ""),
        "track_count": int(raw.get("trackCount") or 0),
        "update_frequency": str(raw.get("updateFrequency") or raw.get("description") or "排行榜"),
    }


def _require_api_success(payload: object, action: str) -> dict:
    result = payload if isinstance(payload, dict) else {}
    code = int(result.get("code") or 0)
    if code in {-460, 301, 302, 401}:
        clear_login()
        raise NeteaseMusicAuthError("网易云登录已失效，请重新扫码")
    if code not in {200, 201}:
        message = str(result.get("message") or result.get("msg") or "").strip()
        raise NeteaseMusicError(f"{action}失败{f'：{message}' if message else f'（code={code}）'}")
    return result


def search_tracks(query: str, *, limit: int = 30, offset: int = 0) -> list[dict]:
    keyword = str(query or "").strip()
    if not keyword:
        raise NeteaseMusicError("缺少搜索关键词")
    session, _, modules = _active_session()
    payload = modules["cloudsearch"].GetSearchResult(
        keyword,
        limit=max(1, min(int(limit), 50)),
        offset=max(0, int(offset)),
        session=session,
    )
    result = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else {}
    songs = result.get("songs") if isinstance(result.get("songs"), list) else []
    return [_map_track(item) for item in songs if isinstance(item, dict)]


def get_daily_recommendations(*, limit: int = 30) -> list[dict]:
    session, _, modules = _active_session()
    payload = _require_api_success(
        modules["get_daily_recommendations"](session=session),
        "网易云每日推荐读取",
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    songs = data.get("dailySongs") if isinstance(data.get("dailySongs"), list) else []
    return [
        _map_track(item)
        for item in songs[: max(1, min(int(limit), 50))]
        if isinstance(item, dict)
    ]


def get_personal_fm(*, limit: int = 10) -> list[dict]:
    clean_limit = max(1, min(int(limit), 30))
    session, _, modules = _active_session()
    payload = _require_api_success(
        modules["get_personal_fm"](clean_limit, session=session),
        "网易云私人 FM 读取",
    )
    songs = payload.get("data") if isinstance(payload.get("data"), list) else []
    return [_map_track(item) for item in songs[:clean_limit] if isinstance(item, dict)]


def list_playlists(*, limit: int = 100, offset: int = 0) -> list[dict]:
    session, profile, modules = _active_session()
    payload = modules["user"].GetUserPlaylists(
        profile["user_id"],
        limit=max(1, min(int(limit), 200)),
        offset=max(0, int(offset)),
        session=session,
    )
    items = payload.get("playlist") if isinstance(payload, dict) and isinstance(payload.get("playlist"), list) else []
    return [_map_playlist(item, profile["user_id"]) for item in items if isinstance(item, dict)]


def get_liked_track_ids() -> list[str]:
    session, profile, modules = _active_session()
    payload = modules["get_user_like_list"](profile["user_id"], session=session)
    ids = payload.get("ids") if isinstance(payload, dict) and isinstance(payload.get("ids"), list) else []
    return [_track_id(item) for item in ids]


def set_track_liked(track_id: object, liked: bool) -> dict:
    clean_track_id = _track_id(track_id)
    session, profile, modules = _active_session()
    payload = modules["track"].SetLikeTrack(
        clean_track_id,
        like=bool(liked),
        userid=profile["user_id"],
        session=session,
    )
    _require_api_success(payload, "网易云红心同步")
    return {"track_id": clean_track_id, "liked": bool(liked)}


def get_recent_tracks(*, limit: int = 100) -> list[dict]:
    session, profile, modules = _active_session()
    payload = modules["get_user_play_record"](profile["user_id"], record_type=0, session=session)
    items = payload.get("allData") if isinstance(payload, dict) and isinstance(payload.get("allData"), list) else []
    tracks = [
        _map_track(item["song"])
        for item in items
        if isinstance(item, dict) and isinstance(item.get("song"), dict)
    ]
    return tracks[: max(1, min(int(limit), 500))]


def list_toplists() -> list[dict]:
    session, _, _ = _active_session()
    try:
        response = session.get(
            "https://music.163.com/api/toplist/detail",
            headers={"User-Agent": "Mozilla/5.0 SumiTalk/1.0", "Referer": "https://music.163.com/"},
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        raise NeteaseMusicError(f"网易云排行榜读取失败: {e}") from e
    except (TypeError, ValueError) as e:
        raise NeteaseMusicError("网易云返回了无效排行榜") from e
    items = payload.get("list") if isinstance(payload, dict) and isinstance(payload.get("list"), list) else []
    return [_map_toplist(item) for item in items if isinstance(item, dict) and item.get("id")]


def update_playlist_tracks(playlist_id: object, track_ids: list[object], operation: str) -> dict:
    clean_playlist_id = _track_id(playlist_id)
    clean_operation = str(operation or "").strip().lower()
    if clean_operation not in {"add", "del"}:
        raise NeteaseMusicError("歌单操作只能是 add 或 del")
    if not isinstance(track_ids, list) or not track_ids:
        raise NeteaseMusicError("至少选择一首歌曲")
    clean_track_ids = list(dict.fromkeys(_track_id(item) for item in track_ids))
    if len(clean_track_ids) > 500:
        raise NeteaseMusicError("单次最多操作 500 首歌曲")
    session, _, modules = _active_session()
    payload = modules["playlist"].SetManipulatePlaylistTracks(
        clean_track_ids,
        playlistId=clean_playlist_id,
        op=clean_operation,
        session=session,
    )
    _require_api_success(payload, "网易云歌单更新")
    return {
        "playlist_id": clean_playlist_id,
        "track_ids": clean_track_ids,
        "operation": clean_operation,
        "count": len(clean_track_ids),
    }


def _track_details(session: Any, modules: dict[str, Any], track_ids: list[str]) -> list[dict]:
    if not track_ids:
        return []
    payload = modules["track"].GetTrackDetail(track_ids, session=session)
    songs = payload.get("songs") if isinstance(payload, dict) and isinstance(payload.get("songs"), list) else []
    by_id = {str(item.get("id") or ""): _map_track(item) for item in songs if isinstance(item, dict)}
    return [by_id[item] for item in track_ids if item in by_id]


def get_playlist_tracks(playlist_id: object, *, limit: int = 300, offset: int = 0) -> dict:
    clean_playlist_id = _track_id(playlist_id)
    session, profile, modules = _active_session()
    payload = modules["playlist"].GetPlaylistInfo(clean_playlist_id, session=session)
    playlist = payload.get("playlist") if isinstance(payload, dict) and isinstance(payload.get("playlist"), dict) else {}
    if not playlist:
        raise NeteaseMusicError("网易云没有返回歌单详情")
    raw_ids = playlist.get("trackIds") if isinstance(playlist.get("trackIds"), list) else []
    all_ids = [_track_id(item.get("id")) for item in raw_ids if isinstance(item, dict) and item.get("id")]
    start = max(0, int(offset))
    selected_ids = all_ids[start : start + max(1, min(int(limit), 500))]
    tracks: list[dict] = []
    for index in range(0, len(selected_ids), 200):
        tracks.extend(_track_details(session, modules, selected_ids[index : index + 200]))
    return {
        "playlist": _map_playlist(playlist, profile["user_id"]),
        "tracks": tracks,
        "total": len(all_ids),
        "offset": start,
    }


def _track_detail(session: Any, modules: dict[str, Any], track_id: str) -> dict:
    tracks = _track_details(session, modules, [track_id])
    if not tracks:
        raise NeteaseMusicError("网易云没有返回歌曲详情")
    return tracks[0]


def get_track_detail(track_id: object) -> dict:
    clean_track_id = _track_id(track_id)
    session, _, modules = _active_session()
    return _track_detail(session, modules, clean_track_id)


def _source_for_track(session: Any, modules: dict[str, Any], track_id: str, level: str) -> dict:
    payload = modules["track"].GetTrackAudioV1([track_id], level=level, encodeType="flac", session=session)
    items = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), list) else []
    item = items[0] if items and isinstance(items[0], dict) else {}
    url = str(item.get("url") or "").strip()
    if not url:
        code = item.get("code") or (payload.get("code") if isinstance(payload, dict) else "")
        raise NeteaseMusicError(f"网易云没有返回可播放曲源{f'（code={code}）' if code else ''}")
    parsed = urlparse(url)
    if parsed.scheme == "http" and _is_netease_audio_host(parsed.hostname or ""):
        url = "https://" + url[len("http://") :]
    url = _validate_audio_url(url)
    return {
        "track_id": track_id,
        "url": url,
        "level": str(item.get("level") or level),
        "audio_format": str(item.get("type") or "").strip().lower(),
        "bitrate": int(item.get("br") or 0),
        "size": int(item.get("size") or 0),
        "md5": str(item.get("md5") or ""),
        "expires_in": int(item.get("expi") or 0),
        "code": int(item.get("code") or 200),
    }


def get_track_source(track_id: object, *, level: str = "standard") -> dict:
    clean_track_id = _track_id(track_id)
    clean_level = _level(level)
    session, _, modules = _active_session()
    return _source_for_track(session, modules, clean_track_id, clean_level)


def _lyrics_for_track(session: Any, modules: dict[str, Any], track_id: str) -> dict:
    payload = modules["track"].GetTrackLyrics(track_id, session=session)
    if not isinstance(payload, dict):
        raise NeteaseMusicError("网易云返回了无效歌词结果")
    lrc = payload.get("lrc") if isinstance(payload.get("lrc"), dict) else {}
    translated = payload.get("tlyric") if isinstance(payload.get("tlyric"), dict) else {}
    romanized = payload.get("romalrc") if isinstance(payload.get("romalrc"), dict) else {}
    return {
        "lyric": str(lrc.get("lyric") or ""),
        "translated_lyric": str(translated.get("lyric") or ""),
        "romanized_lyric": str(romanized.get("lyric") or ""),
    }


def get_track_lyrics(track_id: object) -> dict:
    clean_track_id = _track_id(track_id)
    session, _, modules = _active_session()
    return _lyrics_for_track(session, modules, clean_track_id)


def _is_netease_audio_host(hostname: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in NETEASE_AUDIO_HOST_SUFFIXES)


def _validate_audio_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not _is_netease_audio_host(parsed.hostname or ""):
        raise NeteaseMusicError("网易云返回了不受信任的音频地址")
    return parsed.geturl()


def _download_audio(url: str, *, max_bytes: int = MUSIC_AUDIO_MAX_BYTES) -> tuple[bytes, str, str]:
    current_url = _validate_audio_url(url)
    headers = {"User-Agent": "Mozilla/5.0 SumiTalk/1.0", "Referer": "https://music.163.com/"}
    for _ in range(5):
        try:
            response = requests.get(
                current_url,
                headers=headers,
                stream=True,
                allow_redirects=False,
                timeout=(10, 90),
            )
        except requests.RequestException as e:
            raise NeteaseMusicError(f"下载网易云音频失败: {e}") from e
        if response.status_code in {301, 302, 303, 307, 308}:
            location = str(response.headers.get("Location") or "").strip()
            response.close()
            if not location:
                raise NeteaseMusicError("网易云音频重定向缺少地址")
            current_url = _validate_audio_url(urljoin(current_url, location))
            continue
        if response.status_code != 200:
            response.close()
            raise NeteaseMusicError(f"下载网易云音频失败 status={response.status_code}")
        try:
            length = int(response.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length > max_bytes:
            response.close()
            raise NeteaseMusicError(f"网易云源音频过大，最大 {max_bytes // 1024 // 1024}MB")
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise NeteaseMusicError(f"网易云源音频过大，最大 {max_bytes // 1024 // 1024}MB")
                chunks.append(chunk)
        finally:
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip()
            final_url = str(response.url or current_url)
            response.close()
        audio = b"".join(chunks)
        if not audio:
            raise NeteaseMusicError("网易云返回了空音频")
        return audio, content_type, final_url
    raise NeteaseMusicError("网易云音频重定向次数过多")


def download_track_for_analysis(track_id: object, *, level: str = "lossless") -> dict:
    clean_track_id = _track_id(track_id)
    clean_level = _level(level)
    session, _, modules = _active_session()
    track = _track_detail(session, modules, clean_track_id)
    source = None
    last_source_error: Exception | None = None
    for candidate_level in dict.fromkeys([clean_level, "exhigh", "standard"]):
        try:
            source = _source_for_track(session, modules, clean_track_id, candidate_level)
            if candidate_level != clean_level:
                logger.info(
                    "网易云分析曲源已降级 track_id=%s requested=%s actual=%s",
                    clean_track_id,
                    clean_level,
                    candidate_level,
                )
            break
        except NeteaseMusicError as e:
            last_source_error = e
    if source is None:
        raise NeteaseMusicError(str(last_source_error or "网易云没有返回可分析曲源"))
    audio_bytes, content_type, final_url = _download_audio(source["url"])
    try:
        lyrics = _lyrics_for_track(session, modules, clean_track_id)
    except NeteaseMusicError as e:
        logger.warning("读取网易云歌词失败 track_id=%s error=%s", clean_track_id, e)
        lyrics = {"lyric": "", "translated_lyric": "", "romanized_lyric": ""}
    source_format = str(source.get("audio_format") or "").strip().lower()
    filename = f"netease-{clean_track_id}.{source_format or 'audio'}"
    return {
        "track": track,
        "source": {**source, "url": final_url, "content_type": content_type, "downloaded_size": len(audio_bytes)},
        "lyrics": lyrics,
        "audio_bytes": audio_bytes,
        "filename": filename,
        "mime_type": content_type,
    }
