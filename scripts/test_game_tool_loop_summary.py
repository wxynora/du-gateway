#!/usr/bin/env python3
from __future__ import annotations

import copy
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import tool_result_cache as cache


EXPECTED_SYSTEM_PROMPT = """你负责把同一轮单机游戏中的连续工具调用记录融合成一条准确、自然的中文历史摘要。

严格按照记录顺序整理，只写记录中实际发生的内容。
保留实际执行的动作、关键状态变化、资源获得或消耗、失败原因和终局结果；相同状态只合并表达一次，不得遗漏会影响后续游戏判断的信息。
不得编造、推测或评价操作，不要使用第一人称或第二人称。
只输出一条完整正文，不输出标题、列表、Markdown、JSON、解释或前后缀。"""


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class GameToolLoopSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "runtime.sqlite3"
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE tool_result_cache(
                    id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    window_id TEXT NOT NULL,
                    reply_channel TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _game_entries(tool_name: str = "farm") -> list[dict]:
        return [
            {
                "tool_call_id": "call-1",
                "name": tool_name,
                "arguments": {"command": "播种", "plot": 1},
                "result": {
                    "ok": True,
                    "game_tool_loop": True,
                    "text": "1号地种下小麦，种子减少1",
                },
            },
            {
                "tool_call_id": "call-2",
                "name": tool_name,
                "arguments": {"command": "浇水", "plot": 1},
                "result": {
                    "ok": True,
                    "game_tool_loop": True,
                    "text": "1号地已浇水，体力减少1",
                },
            },
        ]

    def _rows(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT tool_name, summary, window_id, reply_channel FROM tool_result_cache ORDER BY created_at, id"
            ).fetchall()

    def test_target_loop_is_only_snapshotted_and_queued(self) -> None:
        entries = self._game_entries()
        original = copy.deepcopy(entries)
        with mock.patch.object(cache, "_ensure_game_loop_summary_worker") as ensure_worker, mock.patch.object(
            cache._GAME_LOOP_SUMMARY_QUEUE, "put"
        ) as queue_put, mock.patch.object(cache, "_request_game_tool_loop_summary") as request_summary:
            queued = cache.enqueue_game_tool_loop_summary(
                entries,
                window_id="window-1",
                reply_channel="app",
            )

        self.assertTrue(queued)
        ensure_worker.assert_called_once_with()
        request_summary.assert_not_called()
        queued_entries, queued_window, queued_channel = queue_put.call_args.args[0]
        self.assertEqual(original, queued_entries)
        self.assertIsNot(entries, queued_entries)
        self.assertEqual("window-1", queued_window)
        self.assertEqual("app", queued_channel)

    def test_model_success_sends_full_records_and_writes_one_row(self) -> None:
        entries = self._game_entries("random_imitator_td")
        long_text = "完整原始结果起点" + ("甲乙丙丁" * 1800) + "完整原始结果终点"
        entries[0]["arguments"]["full_plan"] = long_text
        entries[1]["result"]["text"] = long_text
        captured: dict = {}

        def fake_post(url, *, headers, json, timeout):
            captured.update(url=url, headers=headers, json=json, timeout=timeout)
            return _FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "先完成部署，随后资源发生变化，最终本局继续进行。"
                            }
                        }
                    ]
                }
            )

        with mock.patch.object(cache.runtime_sqlite, "connect", side_effect=self._connect), mock.patch.object(
            cache, "resolve_siliconflow_api_key", return_value="test-key"
        ), mock.patch.object(cache.requests, "post", side_effect=fake_post) as post:
            inserted = cache._record_game_tool_loop_summary(
                entries,
                window_id="window-2",
                reply_channel="app",
            )

        self.assertEqual(1, inserted)
        post.assert_called_once()
        self.assertEqual("https://api.siliconflow.cn/v1/chat/completions", captured["url"])
        self.assertEqual("Bearer test-key", captured["headers"]["Authorization"])
        self.assertEqual(900, captured["timeout"])
        request_payload = captured["json"]
        self.assertEqual("Qwen/Qwen3-8B", request_payload["model"])
        self.assertFalse(request_payload["stream"])
        self.assertFalse(request_payload["enable_thinking"])
        self.assertEqual(0.1, request_payload["temperature"])
        self.assertEqual({"type": "text"}, request_payload["response_format"])
        self.assertNotIn("max_tokens", request_payload)
        self.assertEqual(EXPECTED_SYSTEM_PROMPT, request_payload["messages"][0]["content"])
        user_prompt = request_payload["messages"][1]["content"]
        self.assertIn("工具名称：random_imitator_td", user_prompt)
        self.assertIn("完整原始结果起点", user_prompt)
        self.assertIn("完整原始结果终点", user_prompt)
        self.assertGreaterEqual(user_prompt.count("甲乙丙丁"), 3600)

        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertEqual("random_imitator_td", rows[0]["tool_name"])
        self.assertEqual(
            "使用 random_imitator_td 连续结果：先完成部署，随后资源发生变化，最终本局继续进行。",
            rows[0]["summary"],
        )
        self.assertEqual("window-2", rows[0]["window_id"])
        self.assertEqual("app", rows[0]["reply_channel"])

    def test_model_failure_has_one_attempt_then_writes_existing_per_entry_summaries(self) -> None:
        entries = self._game_entries("cedareco")
        with mock.patch.object(cache.runtime_sqlite, "connect", side_effect=self._connect), mock.patch.object(
            cache, "resolve_siliconflow_api_key", return_value="test-key"
        ), mock.patch.object(cache.requests, "post", side_effect=requests.Timeout("timeout")) as post, mock.patch.object(
            cache.logger, "warning"
        ):
            inserted = cache._record_game_tool_loop_summary(
                entries,
                window_id="window-3",
                reply_channel="qq",
            )

        self.assertEqual(2, inserted)
        post.assert_called_once()
        rows = self._rows()
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row["summary"].startswith("使用 cedareco 结果：") for row in rows))

    def test_single_mixed_and_non_game_loops_stay_out_of_async_queue(self) -> None:
        cases = [
            self._game_entries()[:1],
            [self._game_entries("farm")[0], self._game_entries("cedareco")[1]],
            [
                {"tool_call_id": "a", "name": "web_search", "arguments": {}, "result": {}},
                {"tool_call_id": "b", "name": "web_search", "arguments": {}, "result": {}},
            ],
        ]
        with mock.patch.object(cache, "_ensure_game_loop_summary_worker") as ensure_worker, mock.patch.object(
            cache._GAME_LOOP_SUMMARY_QUEUE, "put"
        ) as queue_put:
            results = [cache.enqueue_game_tool_loop_summary(entries) for entries in cases]

        self.assertEqual([False, False, False], results)
        ensure_worker.assert_not_called()
        queue_put.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
