#!/usr/bin/env python3
import base64
import io
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from services.image_desc import (
    ANTHROPIC_IMAGE_MAX_LONG_EDGE,
    ANTHROPIC_IMAGE_MAX_PIXELS,
    compress_images_for_anthropic,
)


class _ImageHandler(BaseHTTPRequestHandler):
    image_bytes = b""

    def do_GET(self):
        if self.path == "/image.jpg":
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(self.image_bytes)))
            self.end_headers()
            self.wfile.write(self.image_bytes)
            return
        self.send_response(500)
        self.end_headers()

    def log_message(self, *_args):
        return


class RemoteImageCompressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image = Image.new("RGB", (2400, 1800), (82, 137, 201))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=95)
        _ImageHandler.image_bytes = out.getvalue()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _ImageHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_remote_url_is_downloaded_compressed_and_inlined(self):
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"{self.base_url}/image.jpg"}},
                    ],
                }
            ]
        }

        out_body, stats = compress_images_for_anthropic(body)

        data_url = out_body["messages"][0]["content"][0]["image_url"]["url"]
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        raw = base64.b64decode(data_url.split(",", 1)[1])
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
        self.assertLessEqual(max(width, height), ANTHROPIC_IMAGE_MAX_LONG_EDGE)
        self.assertLessEqual(width * height, ANTHROPIC_IMAGE_MAX_PIXELS)
        self.assertTrue(stats[0]["url_converted"])
        self.assertTrue(stats[0]["changed"])

    def test_one_failed_remote_image_becomes_placeholder_without_dropping_others(self):
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"{self.base_url}/failed.jpg"}},
                        {"type": "text", "text": "继续处理"},
                        {"type": "image_url", "image_url": {"url": f"{self.base_url}/image.jpg"}},
                    ],
                }
            ]
        }

        out_body, stats = compress_images_for_anthropic(body)

        content = out_body["messages"][0]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "【图片】"})
        self.assertEqual(content[1], {"type": "text", "text": "继续处理"})
        self.assertTrue(content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(stats[0]["reason"], "remote_fetch_failed")
        self.assertTrue(stats[0]["replaced_with_placeholder"])
        self.assertTrue(stats[1]["url_converted"])


if __name__ == "__main__":
    unittest.main()
