from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from flask import Flask

from routes.aifarm_proxy import bp as proxy_bp
from services import aifarm_bridge, aifarm_tool


class _FakeResponse:
    def __init__(self, *, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class AIFarmBridgeTest(unittest.TestCase):
    def test_creates_one_local_session_and_keeps_agent_link_private(self):
        human_key = "a" * 32
        payload = {
            "ok": True,
            "humanUrl": f"http://127.0.0.1:8080/ui/{human_key}",
            "playUrl": "http://127.0.0.1:8080/a/secretAgentKey",
            "farm": {"id": "ABC123", "name": "渡的小农场"},
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            aifarm_bridge, "AIFARM_STATE_FILE", Path(tmpdir) / "session.json"
        ), patch.object(
            aifarm_bridge.requests, "post", return_value=_FakeResponse(status_code=201, payload=payload)
        ) as post, patch.object(
            aifarm_bridge.requests, "get", return_value=_FakeResponse(status_code=200)
        ):
            first = aifarm_bridge.ensure_session()
            second = aifarm_bridge.ensure_session()
            public = aifarm_bridge.public_session(first)

            self.assertEqual(first, second)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(public["url"], f"/aifarm/ui/{human_key}")
            self.assertNotIn("play_url", public)
            self.assertNotIn("secretAgentKey", str(public))
            self.assertEqual(first["agent_path"], "/a/secretAgentKey")
            self.assertEqual((Path(tmpdir) / "session.json").stat().st_mode & 0o777, 0o600)

    def test_rejects_invalid_human_url_without_writing_state(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            aifarm_bridge, "AIFARM_STATE_FILE", Path(tmpdir) / "session.json"
        ), patch.object(
            aifarm_bridge.requests,
            "post",
            return_value=_FakeResponse(
                status_code=201,
                payload={"ok": True, "humanUrl": "http://127.0.0.1:8080/ui/not-a-key", "farm": {}},
            ),
        ):
            with self.assertRaises(aifarm_bridge.AIFarmBridgeError):
                aifarm_bridge.ensure_session()
            self.assertFalse((Path(tmpdir) / "session.json").exists())

    def test_agent_action_is_pinned_to_local_upstream_and_keeps_key_private(self):
        state = {
            "human_key": "f" * 32,
            "play_url": "https://untrusted.example/a/AgentKey9",
            "farm_id": "ABC123",
            "farm_name": "渡的小农场",
        }
        upstream_payload = {
            "ok": True,
            "text": "种下了 1 颗普通种子。",
            "farm": {"id": "ABC123", "plots": [{"id": 1, "state": "growing"}]},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "session.json"
            state_file.write_text(json.dumps(state), encoding="utf-8")
            with patch.object(aifarm_bridge, "AIFARM_STATE_FILE", state_file), patch.object(
                aifarm_bridge, "AIFARM_UPSTREAM_URL", "http://127.0.0.1:18080"
            ), patch.object(
                aifarm_bridge.requests,
                "post",
                return_value=_FakeResponse(status_code=200, payload=upstream_payload),
            ) as post:
                result = aifarm_bridge.run_agent_action({"action": "plant", "common": 1, "detail": True})

        self.assertEqual(result, upstream_payload)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:18080/a/AgentKey9/plant")
        self.assertEqual(post.call_args.kwargs["json"], {"common": 1, "detail": True})
        self.assertNotIn("AgentKey9", str(result))

    def test_agent_action_rejects_bad_path_and_secret_rotation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "session.json"
            state_file.write_text(
                json.dumps({"human_key": "e" * 32, "play_url": "http://127.0.0.1:8080/not-agent/key"}),
                encoding="utf-8",
            )
            with patch.object(aifarm_bridge, "AIFARM_STATE_FILE", state_file), patch.object(
                aifarm_bridge.requests, "post"
            ) as post:
                with self.assertRaises(aifarm_bridge.AIFarmBridgeError):
                    aifarm_bridge.run_agent_action({"action": "status"})
                with self.assertRaises(aifarm_bridge.AIFarmBridgeError):
                    aifarm_bridge.run_agent_action({"action": "new-token"})
                post.assert_not_called()


class AIFarmToolTest(unittest.TestCase):
    def test_tool_schema_and_chat_dispatch_use_one_farm_tool(self):
        from services.chat_tools import execute_tool
        from services.gateway_tools import get_gateway_tools_for_inject

        names = [item.get("function", {}).get("name") for item in get_gateway_tools_for_inject()]
        self.assertEqual(names.count("farm"), 1)

        with patch.object(aifarm_tool, "run_agent_action", return_value={"ok": True, "text": "农场已巡视"}) as run:
            result = json.loads(execute_tool("farm", {"action": "status"}))

        self.assertEqual(result, {"ok": True, "text": "农场已巡视"})
        run.assert_called_once_with({"action": "status"})


class AIFarmProxyTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(proxy_bp)
        self.client = app.test_client()

    def test_rewrites_ui_links_and_form_actions(self):
        human_key = "b" * 32
        upstream = _FakeResponse(
            status_code=200,
            content=(
                f'<a href="/ui/{human_key}/codex">图鉴</a>'
                f'<form action="/ui/{human_key}/ranch/collect"></form>'
            ).encode("utf-8"),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
        with patch("routes.aifarm_proxy.requests.request", return_value=upstream) as request_upstream:
            response = self.client.get(f"/aifarm/ui/{human_key}?tab=home")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn(f'href="/aifarm/ui/{human_key}/codex"', body)
        self.assertIn(f'action="/aifarm/ui/{human_key}/ranch/collect"', body)
        self.assertEqual(request_upstream.call_args.kwargs["params"], [("tab", "home")])

    def test_rewrites_post_redirect_but_never_exposes_create_route(self):
        human_key = "c" * 32
        upstream = _FakeResponse(
            status_code=303,
            headers={"Location": f"/ui/{human_key}/ranch?flash=ok"},
        )
        with patch("routes.aifarm_proxy.requests.request", return_value=upstream):
            response = self.client.post(f"/aifarm/ui/{human_key}/ranch/collect", data={})

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], f"/aifarm/ui/{human_key}/ranch?flash=ok")
        self.assertEqual(self.client.post("/aifarm/farms").status_code, 404)

    def test_rejects_ui_path_traversal_before_upstream_request(self):
        human_key = "d" * 32
        with patch("routes.aifarm_proxy.requests.request") as request_upstream:
            response = self.client.get(f"/aifarm/ui/{human_key}/%2e%2e/%2e%2e/farms")

        self.assertEqual(response.status_code, 404)
        request_upstream.assert_not_called()


class AIFarmRealSidecarTest(unittest.TestCase):
    def test_create_plant_and_read_same_farm_through_real_sidecar(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        version = subprocess.run(
            [node, "-p", "Number(process.versions.node.split('.')[0])"],
            check=True,
            capture_output=True,
            text=True,
        )
        if int(version.stdout.strip()) < 20:
            self.skipTest("aifarm requires Node.js >= 20")

        source = Path(__file__).resolve().parents[1] / "vendor" / "aifarm-oss"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = root / "aifarm-runtime"
            shutil.copytree(
                source,
                runtime,
                ignore=shutil.ignore_patterns("node_modules", "data", ".git"),
            )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base_url = f"http://127.0.0.1:{port}"
            env = {
                **os.environ,
                "HOST": "127.0.0.1",
                "PORT": str(port),
                "PUBLIC_BASE_URL": base_url,
                "REGISTRATION_OPEN": "1",
            }
            process = subprocess.Popen(
                [node, "dist/index.js"],
                cwd=runtime,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        output = process.stdout.read() if process.stdout else ""
                        self.fail(f"aifarm sidecar exited early:\n{output}")
                    try:
                        if requests.get(f"{base_url}/", timeout=0.25).status_code == 200:
                            break
                    except requests.RequestException:
                        time.sleep(0.05)
                else:
                    self.fail("aifarm sidecar did not become ready")

                state_file = root / "gateway-session.json"
                child_env = {
                    **os.environ,
                    "AIFARM_UPSTREAM_URL": base_url,
                    "AIFARM_STATE_FILE": str(state_file),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                child_code = (
                    "from services import aifarm_bridge as bridge; "
                    "print(bridge.ensure_session()['farm_id'])"
                )
                children = [
                    subprocess.Popen(
                        [sys.executable, "-c", child_code],
                        cwd=Path(__file__).resolve().parents[1],
                        env=child_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    for _ in range(6)
                ]
                farm_ids = []
                for child in children:
                    stdout, stderr = child.communicate(timeout=10)
                    self.assertEqual(child.returncode, 0, stderr)
                    farm_ids.append(stdout.strip().splitlines()[-1])
                self.assertEqual(len(set(farm_ids)), 1, farm_ids)

                with patch.object(aifarm_bridge, "AIFARM_UPSTREAM_URL", base_url), patch.object(
                    aifarm_bridge, "AIFARM_STATE_FILE", state_file
                ):
                    session = aifarm_bridge.ensure_session()
                    planted = aifarm_bridge.run_agent_action(
                        {"action": "plant", "common": 1, "detail": True}
                    )
                    status = aifarm_bridge.run_agent_action({"action": "status", "detail": True})

                self.assertTrue(planted["ok"], planted["text"])
                self.assertTrue(status["ok"], status["text"])
                self.assertEqual(planted["farm"]["id"], session["farm_id"])
                self.assertEqual(status["farm"]["id"], session["farm_id"])
                self.assertTrue(
                    any(plot["state"] in {"growing", "ripe"} for plot in status["farm"]["plots"]),
                    f"planted={planted!r} status={status!r}",
                )
                self.assertTrue(state_file.exists())
                self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)
                self.assertEqual(
                    state_file.with_suffix(state_file.suffix + ".lock").stat().st_mode & 0o777,
                    0o600,
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                if process.stdout:
                    process.stdout.close()


if __name__ == "__main__":
    unittest.main()
