#!/usr/bin/env python3
"""Focused contract test for persistent Together Watch ticket captures."""

from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile

from PIL import Image


_TEMP_DIR = tempfile.TemporaryDirectory(prefix="watch-ticket-captures-")
_ROOT = Path(_TEMP_DIR.name)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["RUNTIME_STATE_DB"] = str(_ROOT / "runtime.sqlite3")
os.environ["WATCH_VISUAL_CACHE_DIR"] = str(_ROOT / "visual-cache")

from flask import Blueprint, Flask, request  # noqa: E402

from routes.miniapp.watch import register_routes  # noqa: E402
from storage import runtime_sqlite, watch_runtime_store, watch_viewing_store  # noqa: E402


def _jpeg(width: int = 64, height: int = 36, color=(214, 153, 174)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="JPEG")
    return output.getvalue()


def _session(*, media_id: str, viewing_id: str = "", part_index: int = 1) -> dict:
    return watch_runtime_store.create_session(
        device_id="device-a",
        window_id="window-a",
        companion={"id": "assistant", "name": "Assistant"},
        media={
            "id": media_id,
            "source": "bilibili",
            "url": "https://www.bilibili.com/video/BVtest",
            "title": "Test Movie",
            "part_key": media_id,
            "part_index": part_index,
            "part_count": 2,
            "duration_ms": 600_000,
            "content_start_ms": 0,
            "content_end_ms": 600_000,
        },
        mode={
            "knowledge_mode": "known",
            "fear_mode": False,
            "visual_context_mode": "text_only",
        },
        viewing_id=viewing_id,
    )


def _upload(client, *, viewing_id: str, session: dict, at_ms: int, image: bytes):
    media = session["media"]
    playback = session["playback"]
    metadata = {
        "session_id": session["session_id"],
        "media_id": media["id"],
        "timeline_epoch": playback["timeline_epoch"],
        "at_ms": at_ms,
        "width": 64,
        "height": 36,
        "mime_type": "image/jpeg",
    }
    return client.post(
        f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame-captures",
        data={
            "metadata": json.dumps(metadata),
            "image": (BytesIO(image), "capture.jpg", "image/jpeg"),
        },
        headers={"X-Test-Device": "device-a"},
        content_type="multipart/form-data",
    )


def main() -> None:
    runtime_sqlite.ensure_schema()
    app = Flask(__name__)
    bp = Blueprint("watch_capture_test", __name__, url_prefix="/miniapp-api")
    register_routes(bp)
    app.register_blueprint(bp)

    @app.before_request
    def _test_auth() -> None:
        request.environ["miniapp_panel_payload"] = {
            "device_id": request.headers.get("X-Test-Device", "device-a")
        }

    first = _session(media_id="bili:BVtest:p1", part_index=1)
    viewing_id = first["viewing_id"]
    second = _session(
        media_id="bili:BVtest:p2",
        viewing_id=viewing_id,
        part_index=2,
    )
    image = _jpeg()

    with app.test_client() as client:
        invalid = _upload(
            client,
            viewing_id=viewing_id,
            session=first,
            at_ms=45_000,
            image=b"not-an-image",
        )
        assert invalid.status_code == 400, invalid.get_data(as_text=True)

        first_response = _upload(
            client,
            viewing_id=viewing_id,
            session=first,
            at_ms=45_000,
            image=image,
        )
        assert first_response.status_code == 201, first_response.get_data(as_text=True)
        first_capture = first_response.get_json()["capture"]
        assert first_capture == {
            "frame_id": first_capture["frame_id"],
            "media_id": "bili:BVtest:p1",
            "at_ms": 45_000,
            "width": 64,
            "height": 36,
            "mime_type": "image/jpeg",
            "image_url": (
                f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame-captures/"
                f"{first_capture['frame_id']}/image"
            ),
        }

        second_response = _upload(
            client,
            viewing_id=viewing_id,
            session=second,
            at_ms=15_000,
            image=_jpeg(color=(90, 120, 180)),
        )
        assert second_response.status_code == 201, second_response.get_data(as_text=True)
        second_capture = second_response.get_json()["capture"]

        forbidden = client.get(
            f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame-captures",
            headers={"X-Test-Device": "device-b"},
        )
        assert forbidden.status_code == 403, forbidden.get_data(as_text=True)

        wrong_epoch_session = dict(first)
        wrong_epoch_session["playback"] = dict(first["playback"])
        wrong_epoch_session["playback"]["timeline_epoch"] += 1
        wrong_epoch = _upload(
            client,
            viewing_id=viewing_id,
            session=wrong_epoch_session,
            at_ms=50_000,
            image=image,
        )
        assert wrong_epoch.status_code == 409, wrong_epoch.get_data(as_text=True)

        wrong_media_session = dict(first)
        wrong_media_session["media"] = dict(first["media"])
        wrong_media_session["media"]["id"] = "bili:BVother:p1"
        wrong_media = _upload(
            client,
            viewing_id=viewing_id,
            session=wrong_media_session,
            at_ms=50_000,
            image=image,
        )
        assert wrong_media.status_code == 409, wrong_media.get_data(as_text=True)

        saved = client.delete(
            f"/miniapp-api/watch/sessions/{first['session_id']}?viewing_action=save_progress",
            headers={"X-Test-Device": "device-a"},
        )
        assert saved.status_code == 200, saved.get_data(as_text=True)
        completed = client.delete(
            f"/miniapp-api/watch/sessions/{second['session_id']}?viewing_action=complete",
            headers={"X-Test-Device": "device-a"},
        )
        assert completed.status_code == 200, completed.get_data(as_text=True)

        captures = client.get(
            f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame-captures",
            headers={"X-Test-Device": "device-a"},
        )
        assert captures.status_code == 200, captures.get_data(as_text=True)
        listed = captures.get_json()["captures"]
        assert [item["frame_id"] for item in listed] == [
            first_capture["frame_id"],
            second_capture["frame_id"],
        ]

        selected = client.put(
            f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame",
            json={"capture_id": first_capture["frame_id"]},
            headers={"X-Test-Device": "device-a"},
        )
        assert selected.status_code == 200, selected.get_data(as_text=True)
        summary = selected.get_json()["viewing_summary"]
        assert summary["ticket_back_frame"]["frame_id"] == first_capture["frame_id"]
        assert summary["ticket"]["back_frame"]["frame_id"] == first_capture["frame_id"]

        capture_image = client.get(
            first_capture["image_url"],
            headers={"X-Test-Device": "device-a"},
        )
        assert capture_image.status_code == 200
        assert capture_image.content_type == "image/jpeg"
        assert "max-age=31536000" in capture_image.headers.get("Cache-Control", "")
        assert capture_image.data == image

        selected_image = client.get(
            f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame/image",
            headers={"X-Test-Device": "device-a"},
        )
        assert selected_image.status_code == 200
        assert selected_image.data == image

        cleared = client.delete(
            f"/miniapp-api/watch/viewings/{viewing_id}/ticket-frame",
            headers={"X-Test-Device": "device-a"},
        )
        assert cleared.status_code == 200, cleared.get_data(as_text=True)
        assert cleared.get_json()["viewing_summary"]["ticket_back_frame"] is None
        assert watch_viewing_store.get_ticket_frame_capture(
            viewing_id, first_capture["frame_id"]
        ) is not None
        still_readable = client.get(
            first_capture["image_url"],
            headers={"X-Test-Device": "device-a"},
        )
        assert still_readable.status_code == 200

    print("watch ticket frame capture contract: ok")


if __name__ == "__main__":
    try:
        main()
    finally:
        _TEMP_DIR.cleanup()
