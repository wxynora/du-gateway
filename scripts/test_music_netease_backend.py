#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from flask import Blueprint, Flask

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from routes.miniapp.music_netease import register_routes
from services import netease_music
from storage import music_melody_store


class _FakeSession:
    def __init__(self, state: dict | None = None):
        self.state = dict(state or {})

    def request(self, method, url, *args, **kwargs):
        raise AssertionError("fake session must not perform network requests")


def _fake_pyncm_modules() -> dict:
    def dump_session(session: _FakeSession) -> str:
        return json.dumps(session.state, sort_keys=True)

    def load_session(payload: str) -> _FakeSession:
        return _FakeSession(json.loads(payload))

    login = SimpleNamespace(
        LoginQrcodeUnikey=lambda *, session: {"unikey": "qr_key_123456"},
        GetLoginQRCodeUrl=lambda key, *, session: f"https://music.163.com/login?codekey={key}",
        LoginQrcodeCheck=lambda key, *, session: session.state.update({"scanned": True}) or {"code": 803, "message": "授权登录成功"},
        GetCurrentLoginStatus=lambda *, session: {
            "code": 200,
            "account": {"id": 42, "vipType": 11},
            "profile": {"userId": 42, "nickname": "小玥", "avatarUrl": "https://p1.music.126.net/avatar.jpg"},
        },
    )
    return {
        "Session": _FakeSession,
        "DumpSessionAsString": dump_session,
        "LoadSessionFromString": load_session,
        "WriteLoginInfo": lambda status, session: session.state.update({"logged_in": True}),
        "cloudsearch": SimpleNamespace(),
        "login": login,
        "playlist": SimpleNamespace(),
        "track": SimpleNamespace(),
        "user": SimpleNamespace(),
    }


class NeteaseMusicStateTest(unittest.TestCase):
    def test_analysis_source_identity_survives_local_cache_normalization(self) -> None:
        with tempfile.TemporaryDirectory(prefix="du_netease_analysis_source_") as tmp:
            cache_file = Path(tmp) / "music-cache.json"
            with (
                mock.patch.object(music_melody_store, "LOCAL_MUSIC_MELODY_CACHE_FILE", cache_file),
                mock.patch.object(music_melody_store, "_s3_client", return_value=None),
            ):
                entry = music_melody_store.save_music_melody_entry(
                    "Supernova",
                    "Laszlo",
                    "openrouter",
                    "gemini-test",
                    "v1",
                    "00:00-00:12 前奏",
                )
                linked = music_melody_store.update_music_melody_source_by_id(
                    entry["id"],
                    source_provider="netease",
                    source_track_id="29732235",
                    source_cover_url="https://p1.music.126.net/cover.jpg",
                )
                restored = music_melody_store.get_music_melody_entry_by_id(entry["id"])

            self.assertEqual(linked["source_provider"], "netease")
            self.assertEqual(restored["source_track_id"], "29732235")
            self.assertEqual(restored["source_cover_url"], "https://p1.music.126.net/cover.jpg")

    def test_qr_login_round_trip_stays_local_and_private(self) -> None:
        with tempfile.TemporaryDirectory(prefix="du_netease_state_test_") as tmp:
            state_file = Path(tmp) / "netease.json"
            lock_file = Path(tmp) / ".netease.lock"
            with (
                mock.patch.object(netease_music, "NETEASE_SESSION_FILE", state_file),
                mock.patch.object(netease_music, "NETEASE_SESSION_LOCK_FILE", lock_file),
                mock.patch.object(netease_music, "_pyncm_modules", side_effect=_fake_pyncm_modules),
            ):
                created = netease_music.create_login_qr()
                checked = netease_music.check_login_qr(created["key"])
                status = netease_music.get_login_status()

            self.assertEqual(created["qr_url"], "https://music.163.com/login?codekey=qr_key_123456")
            self.assertTrue(checked["logged_in"])
            self.assertEqual(checked["profile"]["user_id"], "42")
            self.assertTrue(status["logged_in"])
            self.assertEqual(os.stat(state_file).st_mode & 0o777, 0o600)
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["pending"], {})
            self.assertTrue(saved["active_session"])

    def test_remote_login_expiry_clears_persisted_session(self) -> None:
        with tempfile.TemporaryDirectory(prefix="du_netease_expired_state_") as tmp:
            state_file = Path(tmp) / "netease.json"
            lock_file = Path(tmp) / ".netease.lock"
            state_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "active_session": json.dumps({"logged_in": True}),
                        "active_profile": {"user_id": "42", "nickname": "小玥"},
                        "pending": {},
                    }
                ),
                encoding="utf-8",
            )
            modules = _fake_pyncm_modules()
            modules["login"].GetCurrentLoginStatus = lambda *, session: {"code": 301}
            with (
                mock.patch.object(netease_music, "NETEASE_SESSION_FILE", state_file),
                mock.patch.object(netease_music, "NETEASE_SESSION_LOCK_FILE", lock_file),
                mock.patch.object(netease_music, "_pyncm_modules", return_value=modules),
            ):
                status = netease_music.get_login_status()

            self.assertFalse(status["logged_in"])
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["active_session"], "")
            self.assertEqual(saved["active_profile"], {})

    def test_daily_recommendations_and_personal_fm_map_real_payloads(self) -> None:
        daily_calls = []
        fm_calls = []
        song = {
            "id": 29732235,
            "name": "Supernova",
            "ar": [{"name": "Laszlo"}],
            "al": {"name": "夜航", "picUrl": "https://p1.music.126.net/cover.jpg"},
            "dt": 215000,
        }
        modules = {
            "get_daily_recommendations": lambda *, session: daily_calls.append(session) or {
                "code": 200,
                "data": {"dailySongs": [song]},
            },
            "get_personal_fm": lambda limit, *, session: fm_calls.append((limit, session)) or {
                "code": 200,
                "data": [song],
            },
        }
        session = object()
        with mock.patch.object(
            netease_music,
            "_active_session",
            return_value=(session, {"user_id": "42"}, modules),
        ):
            daily = netease_music.get_daily_recommendations(limit=30)
            fm = netease_music.get_personal_fm(limit=10)

        self.assertEqual(daily[0]["title"], "Supernova")
        self.assertEqual(daily[0]["artist"], "Laszlo")
        self.assertEqual(fm[0]["cover_url"], "https://p1.music.126.net/cover.jpg")
        self.assertEqual(daily_calls, [session])
        self.assertEqual(fm_calls, [(10, session)])

    def test_track_source_keeps_real_netease_format_metadata(self) -> None:
        track_api = SimpleNamespace(
            GetTrackAudioV1=lambda ids, level, encodeType, session: {
                "code": 200,
                "data": [
                    {
                        "id": int(ids[0]),
                        "url": "http://m801.music.126.net/song.flac",
                        "type": "flac",
                        "level": level,
                        "br": 999000,
                        "size": 123456,
                        "md5": "abc",
                        "code": 200,
                    }
                ],
            }
        )
        with mock.patch.object(
            netease_music,
            "_active_session",
            return_value=(object(), {"user_id": "42"}, {"track": track_api}),
        ):
            source = netease_music.get_track_source("29732235", level="lossless")

        self.assertEqual(source["audio_format"], "flac")
        self.assertEqual(source["level"], "lossless")
        self.assertTrue(source["url"].startswith("https://m801.music.126.net/"))

    def test_liked_tracks_and_toggle_use_the_active_account(self) -> None:
        like_calls = []
        modules = {
            "get_user_like_list": lambda user_id, *, session: {"code": 200, "ids": [29732235, 347230]},
            "track": SimpleNamespace(
                SetLikeTrack=lambda track_id, like, userid, session: like_calls.append(
                    (track_id, like, userid, session)
                ) or {"code": 200},
            ),
        }
        session = object()
        with mock.patch.object(
            netease_music,
            "_active_session",
            return_value=(session, {"user_id": "42"}, modules),
        ):
            liked_ids = netease_music.get_liked_track_ids()
            result = netease_music.set_track_liked("29732235", False)

        self.assertEqual(liked_ids, ["29732235", "347230"])
        self.assertEqual(result, {"track_id": "29732235", "liked": False})
        self.assertEqual(like_calls, [("29732235", False, "42", session)])

    def test_recent_tracks_maps_real_record_payload(self) -> None:
        modules = {
            "get_user_play_record": lambda user_id, record_type, *, session: {
                "code": 200,
                "allData": [
                    {
                        "song": {
                            "id": 29732235,
                            "name": "Supernova",
                            "ar": [{"name": "Laszlo"}],
                            "al": {"name": "夜航", "picUrl": "https://p1.music.126.net/cover.jpg"},
                            "dt": 215000,
                        }
                    }
                ],
            }
        }
        with mock.patch.object(
            netease_music,
            "_active_session",
            return_value=(object(), {"user_id": "42"}, modules),
        ):
            tracks = netease_music.get_recent_tracks(limit=10)

        self.assertEqual(tracks[0]["id"], "29732235")
        self.assertEqual(tracks[0]["title"], "Supernova")
        self.assertEqual(tracks[0]["artist"], "Laszlo")

    def test_playlist_mutation_only_accepts_real_ids_and_supported_operations(self) -> None:
        calls = []
        modules = {
            "playlist": SimpleNamespace(
                SetManipulatePlaylistTracks=lambda track_ids, playlistId, op, session: calls.append(
                    (track_ids, playlistId, op, session)
                ) or {"code": 200},
            ),
        }
        session = object()
        with mock.patch.object(
            netease_music,
            "_active_session",
            return_value=(session, {"user_id": "42"}, modules),
        ):
            result = netease_music.update_playlist_tracks(
                "123456",
                ["29732235", "29732235", "347230"],
                "add",
            )

        self.assertEqual(result["count"], 2)
        self.assertEqual(calls, [(["29732235", "347230"], "123456", "add", session)])
        with self.assertRaisesRegex(netease_music.NeteaseMusicError, "add 或 del"):
            netease_music.update_playlist_tracks("123456", ["29732235"], "move")

    def test_audio_download_rejects_non_netease_redirect(self) -> None:
        response = mock.Mock()
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/private"}
        response.close = mock.Mock()
        with mock.patch.object(netease_music.requests, "get", return_value=response):
            with self.assertRaisesRegex(netease_music.NeteaseMusicError, "不受信任"):
                netease_music._download_audio("https://m801.music.126.net/song.mp3", max_bytes=1024)

    def test_explicit_analysis_source_falls_back_when_lossless_is_unavailable(self) -> None:
        def source_for_level(session, modules, track_id, level):
            if level in {"lossless", "exhigh"}:
                raise netease_music.NeteaseMusicError(f"{level} unavailable")
            return {
                "track_id": track_id,
                "url": "https://m801.music.126.net/song.mp3",
                "audio_format": "mp3",
                "level": "standard",
            }

        with (
            mock.patch.object(netease_music, "_active_session", return_value=(object(), {}, {})),
            mock.patch.object(
                netease_music,
                "_track_detail",
                return_value={"id": "29732235", "title": "Supernova", "duration_ms": 215000},
            ),
            mock.patch.object(netease_music, "_source_for_track", side_effect=source_for_level) as source,
            mock.patch.object(
                netease_music,
                "_download_audio",
                return_value=(b"mp3-bytes", "audio/mpeg", "https://m801.music.126.net/song.mp3"),
            ),
            mock.patch.object(netease_music, "_lyrics_for_track", return_value={"lyric": ""}),
        ):
            prepared = netease_music.download_track_for_analysis("29732235", level="lossless")

        self.assertEqual(prepared["source"]["level"], "standard")
        self.assertEqual([call.args[3] for call in source.call_args_list], ["lossless", "exhigh", "standard"])


class NeteaseMusicRouteBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        bp = Blueprint("music_netease_test", __name__, url_prefix="/miniapp-api")
        register_routes(bp)
        app.register_blueprint(bp)
        self.client = app.test_client()

    def test_resolving_playback_source_never_calls_analyzer(self) -> None:
        source = {
            "track_id": "29732235",
            "url": "https://m801.music.126.net/song.flac",
            "audio_format": "flac",
            "level": "lossless",
        }
        with (
            mock.patch("routes.miniapp.music_netease.get_track_source", return_value=source),
            mock.patch("routes.miniapp.music_netease.analyze_music_melody") as analyze,
            mock.patch("routes.miniapp.music_netease.download_track_for_analysis") as download,
        ):
            response = self.client.get("/miniapp-api/music/netease/tracks/29732235/source?level=lossless")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"]["audio_format"], "flac")
        analyze.assert_not_called()
        download.assert_not_called()

    def test_explicit_analyze_route_is_the_only_model_entry(self) -> None:
        prepared = {
            "track": {
                "id": "29732235",
                "title": "Supernova",
                "artist": "Laszlo",
                "duration_ms": 215000,
            },
            "source": {"audio_format": "flac", "level": "lossless", "downloaded_size": 1234},
            "lyrics": {"lyric": "[00:01.00]start"},
            "audio_bytes": b"real-flac-bytes",
            "filename": "netease-29732235.flac",
            "mime_type": "audio/flac",
        }
        analysis = {"ok": True, "cached": False, "entry": {"id": "analysis-1"}}
        with (
            mock.patch("routes.miniapp.music_netease.download_track_for_analysis", return_value=prepared) as download,
            mock.patch("routes.miniapp.music_netease.analyze_music_melody", return_value=analysis) as analyze,
            mock.patch(
                "routes.miniapp.music_netease.update_music_melody_source_by_id",
                return_value={
                    "id": "analysis-1",
                    "source_provider": "netease",
                    "source_track_id": "29732235",
                },
            ) as link_source,
        ):
            response = self.client.post(
                "/miniapp-api/music/netease/tracks/29732235/analyze",
                json={"level": "lossless"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["entry"]["id"], "analysis-1")
        self.assertEqual(response.get_json()["entry"]["source_track_id"], "29732235")
        download.assert_called_once_with("29732235", level="lossless")
        analyze.assert_called_once()
        kwargs = analyze.call_args.kwargs
        self.assertEqual(kwargs["audio_bytes"], b"real-flac-bytes")
        self.assertEqual(kwargs["filename"], "netease-29732235.flac")
        self.assertEqual(kwargs["lyrics_text"], "[00:01.00]start")
        self.assertEqual(kwargs["duration_seconds"], 215.0)
        link_source.assert_called_once_with(
            "analysis-1",
            source_provider="netease",
            source_track_id="29732235",
            source_cover_url="",
        )

    def test_like_and_playlist_mutation_routes_forward_explicit_actions(self) -> None:
        with (
            mock.patch(
                "routes.miniapp.music_netease.set_track_liked",
                return_value={"track_id": "29732235", "liked": True},
            ) as like,
            mock.patch(
                "routes.miniapp.music_netease.update_playlist_tracks",
                return_value={
                    "playlist_id": "123456",
                    "track_ids": ["29732235"],
                    "operation": "del",
                    "count": 1,
                },
            ) as update,
            mock.patch("routes.miniapp.music_netease.analyze_music_melody") as analyze,
        ):
            liked = self.client.post(
                "/miniapp-api/music/netease/tracks/29732235/like",
                json={"liked": True},
            )
            changed = self.client.post(
                "/miniapp-api/music/netease/playlists/123456/tracks",
                json={"track_ids": ["29732235"], "operation": "del"},
            )

        self.assertEqual(liked.status_code, 200)
        self.assertEqual(changed.status_code, 200)
        like.assert_called_once_with("29732235", True)
        update.assert_called_once_with("123456", ["29732235"], "del")
        analyze.assert_not_called()

    def test_daily_recommendations_and_personal_fm_routes_forward_limits(self) -> None:
        item = {"id": "29732235", "title": "Supernova"}
        with (
            mock.patch(
                "routes.miniapp.music_netease.get_daily_recommendations",
                return_value=[item],
            ) as daily,
            mock.patch(
                "routes.miniapp.music_netease.get_personal_fm",
                return_value=[item],
            ) as fm,
        ):
            daily_response = self.client.get(
                "/miniapp-api/music/netease/recommendations/daily?limit=25"
            )
            fm_response = self.client.get(
                "/miniapp-api/music/netease/personal-fm?limit=8"
            )

        self.assertEqual(daily_response.status_code, 200)
        self.assertEqual(fm_response.status_code, 200)
        self.assertEqual(daily_response.get_json()["items"], [item])
        self.assertEqual(fm_response.get_json()["items"], [item])
        daily.assert_called_once_with(limit=25)
        fm.assert_called_once_with(limit=8)


if __name__ == "__main__":
    unittest.main()
