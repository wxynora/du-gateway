from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Blueprint, Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes.miniapp.longterm_memory import register_routes
from services import du_longterm_memory


class LongtermMemoryApiTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        blueprint = Blueprint("longterm_memory_test", __name__, url_prefix="/miniapp-api")
        register_routes(blueprint)
        app.register_blueprint(blueprint)
        app.testing = True
        self.client = app.test_client()

    def test_returns_only_formal_latest_fields(self):
        latest = {
            "schema_version": 1,
            "content": "正式长期记忆",
            "covered_through": "2026-07-12",
            "updated_at": "2026-07-28T14:31:00+08:00",
            "model": "deepseek-chat",
            "prompt_version": "longterm-diary-auto-v1",
            "source_increment_ids": ["2026-07-13_2026-07-15"],
            "last_increment_id": "2026-07-13_2026-07-15",
            "history": [{"content": "旧版"}],
            "increments": [{"content": "增量素材"}],
        }
        with patch.object(
            du_longterm_memory,
            "get_latest_longterm_memory",
            return_value=latest,
        ) as getter:
            response = self.client.get("/miniapp-api/longterm-memory")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "ok": True,
                "exists": True,
                "content": "正式长期记忆",
                "covered_through": "2026-07-12",
                "updated_at": "2026-07-28T14:31:00+08:00",
                "schema_version": 1,
                "model": "deepseek-chat",
                "prompt_version": "longterm-diary-auto-v1",
            },
        )
        getter.assert_called_once_with()

    def test_missing_latest_is_an_empty_success(self):
        with patch.object(
            du_longterm_memory,
            "get_latest_longterm_memory",
            return_value=None,
        ) as getter:
            response = self.client.get("/miniapp-api/longterm-memory")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "ok": True,
                "exists": False,
                "content": "",
                "covered_through": "",
                "updated_at": "",
                "schema_version": None,
                "model": "",
                "prompt_version": "",
            },
        )
        getter.assert_called_once_with()

    def test_read_failure_returns_stable_error(self):
        with patch.object(
            du_longterm_memory,
            "get_latest_longterm_memory",
            side_effect=RuntimeError("R2 unavailable"),
        ) as getter:
            response = self.client.get("/miniapp-api/longterm-memory")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.get_json(),
            {"ok": False, "error": "longterm_memory_read_failed"},
        )
        getter.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
