#!/usr/bin/env python3
"""Pure-local regression tests for sticker compression before mocked R2 writes."""

from __future__ import annotations

from contextlib import ExitStack
from io import BytesIO
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import r2_sticker_store


def _image_bytes(image_format: str, size: tuple[int, int], color: tuple[int, ...]) -> bytes:
    output = BytesIO()
    mode = "RGBA" if len(color) == 4 else "RGB"
    Image.new(mode, size, color).save(output, format=image_format)
    return output.getvalue()


def _upload_with_mocked_r2(filename: str, content: bytes, content_type: str) -> tuple[str | None, Mock]:
    client = Mock()
    with ExitStack() as stack:
        stack.enter_context(patch.object(r2_sticker_store, "get_sticker_tag_keys", return_value={"happy"}))
        stack.enter_context(patch.object(r2_sticker_store, "_s3_client", return_value=client))
        stack.enter_context(patch.object(r2_sticker_store, "rebuild_stickers_mapping_from_r2", return_value={}))
        stack.enter_context(patch.object(r2_sticker_store, "save_stickers_mapping", return_value=True))
        stack.enter_context(patch.object(r2_sticker_store, "uuid4", return_value=SimpleNamespace(hex="fixed")))
        key = r2_sticker_store.upload_sticker_file("happy", filename, content, content_type)
    return key, client


def _stored_image(client: Mock) -> tuple[Image.Image, dict]:
    kwargs = client.put_object.call_args.kwargs
    image = Image.open(BytesIO(kwargs["Body"]))
    image.load()
    return image, kwargs


def test_landscape_png_is_downscaled_before_r2() -> None:
    key, client = _upload_with_mocked_r2(
        "wide.png",
        _image_bytes("PNG", (900, 450), (220, 40, 80, 255)),
        "image/png",
    )
    image, kwargs = _stored_image(client)
    assert key == "stickers/happy/fixed.png"
    assert image.size == (300, 150)
    assert kwargs["ContentType"] == "image/png"


def test_portrait_jpeg_is_downscaled_before_r2() -> None:
    key, client = _upload_with_mocked_r2(
        "tall.jpg",
        _image_bytes("JPEG", (200, 600), (50, 120, 220)),
        "image/jpeg",
    )
    image, kwargs = _stored_image(client)
    assert key == "stickers/happy/fixed.jpg"
    assert image.size == (100, 300)
    assert kwargs["ContentType"] == "image/jpeg"


def test_animated_gif_keeps_frames_after_downscale() -> None:
    first = Image.new("RGBA", (600, 300), (255, 0, 0, 255))
    second = Image.new("RGBA", (600, 300), (0, 0, 255, 255))
    source = BytesIO()
    first.save(
        source,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=[80, 120],
        loop=0,
    )

    key, client = _upload_with_mocked_r2("animated.gif", source.getvalue(), "image/gif")
    kwargs = client.put_object.call_args.kwargs
    with Image.open(BytesIO(kwargs["Body"])) as stored:
        assert key == "stickers/happy/fixed.gif"
        assert stored.size == (300, 150)
        assert stored.n_frames == 2
        assert kwargs["ContentType"] == "image/gif"


def test_invalid_image_never_reaches_r2() -> None:
    key, client = _upload_with_mocked_r2("fake.png", b"not-an-image", "image/png")
    assert key is None
    client.put_object.assert_not_called()


if __name__ == "__main__":
    test_landscape_png_is_downscaled_before_r2()
    test_portrait_jpeg_is_downscaled_before_r2()
    test_animated_gif_keeps_frames_after_downscale()
    test_invalid_image_never_reaches_r2()
    print("sticker upload compression tests passed")
