#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
storage_package = types.ModuleType("storage")
storage_package.__path__ = [str(ROOT / "storage")]
sys.modules.setdefault("storage", storage_package)

from flask import Blueprint, Flask

import config
from routes.miniapp.panel_auth import register_routes
from storage import miniapp_panel_store
from utils import miniapp_panel_auth


class NativePairingBackendTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_store_path = miniapp_panel_store.MINIAPP_PANEL_TRUSTED_DEVICES_FILE
        self.old_password = miniapp_panel_auth.MINIAPP_PANEL_PASSWORD
        self.old_signing_secret = miniapp_panel_auth.MINIAPP_PANEL_SIGNING_SECRET
        self.old_ttl = miniapp_panel_auth.MINIAPP_PANEL_TOKEN_TTL_SECONDS
        self.old_pairing_secret = config.SUMITALK_NATIVE_PAIRING_SECRET

        miniapp_panel_store.MINIAPP_PANEL_TRUSTED_DEVICES_FILE = (
            Path(self.temp_dir.name) / "trusted-devices.json"
        )
        miniapp_panel_auth.MINIAPP_PANEL_PASSWORD = "panel-password"
        miniapp_panel_auth.MINIAPP_PANEL_SIGNING_SECRET = "panel-signing-secret"
        miniapp_panel_auth.MINIAPP_PANEL_TOKEN_TTL_SECONDS = 3600
        config.SUMITALK_NATIVE_PAIRING_SECRET = "native-pairing-secret"

        app = Flask(__name__)
        bp = Blueprint("native_pairing_test", __name__, url_prefix="/miniapp-api")
        register_routes(bp)
        app.register_blueprint(bp)
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        miniapp_panel_store.MINIAPP_PANEL_TRUSTED_DEVICES_FILE = self.old_store_path
        miniapp_panel_auth.MINIAPP_PANEL_PASSWORD = self.old_password
        miniapp_panel_auth.MINIAPP_PANEL_SIGNING_SECRET = self.old_signing_secret
        miniapp_panel_auth.MINIAPP_PANEL_TOKEN_TTL_SECONDS = self.old_ttl
        config.SUMITALK_NATIVE_PAIRING_SECRET = self.old_pairing_secret
        self.temp_dir.cleanup()

    def pair(self, device_id="device_native_install_001", secret="native-pairing-secret"):
        return self.client.post(
            "/miniapp-api/panel-auth/native-device/pair",
            headers={"X-SumiTalk-Pairing-Secret": secret},
            json={"device_id": device_id, "device_name": "Xiaomi 15"},
        )

    def test_pairing_issues_existing_panel_token_without_login(self):
        response = self.pair()

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual("device_native_install_001", body["device_id"])
        ok, payload, code = miniapp_panel_auth.verify_panel_token(body["panel_token"])
        self.assertTrue(ok, code)
        self.assertEqual("device_native_install_001", payload["device_id"])
        self.assertTrue(miniapp_panel_store.is_trusted_device("device_native_install_001"))

    def test_pairing_requires_shared_secret(self):
        response = self.pair(secret="wrong")

        self.assertEqual(401, response.status_code)
        self.assertEqual("native_pairing_unauthorized", response.get_json()["code"])
        self.assertFalse(miniapp_panel_store.is_trusted_device("device_native_install_001"))

    def test_revoked_installation_cannot_silently_pair_again(self):
        self.assertEqual(200, self.pair().status_code)
        self.assertTrue(miniapp_panel_store.revoke_trusted_device("device_native_install_001"))

        response = self.pair()

        self.assertEqual(403, response.status_code)
        self.assertEqual("device_revoked", response.get_json()["code"])
        self.assertFalse(miniapp_panel_store.is_trusted_device("device_native_install_001"))

    def test_missing_native_device_record_is_recoverable_for_installed_app(self):
        token, _ = miniapp_panel_auth.issue_panel_token(
            subject="device:device_native_install_001",
            device_id="device_native_install_001",
        )

        with self.app.test_request_context(
            "/miniapp-api/upstreams",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "SumiTalk Native Android",
            },
        ):
            response, status = miniapp_panel_auth.enforce_panel_token()

        self.assertEqual(401, status)
        self.assertEqual("not_trusted", response.get_json()["code"])
        self.assertEqual("原生设备未配对，请重新连接", response.get_json()["error"])

    def test_missing_browser_record_stays_revoked_for_web_client(self):
        token, _ = miniapp_panel_auth.issue_panel_token(
            subject="device:browser_001",
            device_id="browser_001",
        )

        with self.app.test_request_context(
            "/miniapp-api/upstreams",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0",
            },
        ):
            response, status = miniapp_panel_auth.enforce_panel_token()

        self.assertEqual(403, status)
        self.assertEqual("这个浏览器已被撤销，请重新验证", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
