#!/usr/bin/env python3
"""定向回归：已点名链路不再静默裁剪、截断或只取最后若干条。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory_vector import embedding_client
from pipeline import pipeline
from services import deepseek_summary, du_daily, dynamic_layer_ds


def test_dynamic_query_and_embedding_keep_full_text() -> None:
    long_text = "查询正文" * 3000
    query = dynamic_layer_ds._build_query_from_round([{"role": "user", "content": long_text}])
    assert query == long_text
    assert embedding_client.normalize_text(long_text) == long_text

    captured: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, rows):
            self._rows = rows

        def json(self):
            return {"result": {"data": self._rows}}

    original_post = embedding_client.requests.post
    original_account = embedding_client.CF_ACCOUNT_ID
    original_token = embedding_client.CF_API_TOKEN
    try:
        embedding_client.CF_ACCOUNT_ID = "test-account"
        embedding_client.CF_API_TOKEN = "test-token"

        def fake_post(_url, *, headers, json, timeout):
            _ = headers, timeout
            captured.append(json)
            texts = json["text"] if isinstance(json["text"], list) else [json["text"]]
            return FakeResponse([[float(index)] for index, _text in enumerate(texts, start=1)])

        embedding_client.requests.post = fake_post
        assert embedding_client._embed_via_cloudflare(long_text) == [1.0]
        assert embedding_client._embed_many_via_cloudflare([long_text, "第二条"], model="@cf/baai/bge-m3") == [
            [1.0],
            [2.0],
        ]
    finally:
        embedding_client.requests.post = original_post
        embedding_client.CF_ACCOUNT_ID = original_account
        embedding_client.CF_API_TOKEN = original_token

    assert len(captured) == 2
    assert all("truncate_inputs" not in payload for payload in captured)
    assert captured[0]["text"] == long_text
    assert captured[1]["text"][0] == long_text


def test_du_daily_keeps_all_events_and_full_text() -> None:
    messages = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"第{index}条-" + ("长正文" * 100),
        }
        for index in range(9)
    ]
    facts = du_daily._extract_recent_dialogue_facts(messages)
    assert len(facts) == len(messages)
    assert facts[0].endswith("长正文" * 100)
    assert facts[-1].endswith("长正文" * 100)

    events = [f"{index:02d}:00 事件{index}" for index in range(12)]
    assert du_daily._normalize_today_events(events) == events

    long_summary = "总结正文" * 400
    assert du_daily._normalize_summary_text(long_summary) == long_summary

    fallback = du_daily._fallback_compress_today_lines(events)
    assert "事件0" in fallback
    assert "事件11" in fallback

    trigger = {"kind": "conflict", "reason": "测试", "facts": events}
    inject = du_daily.format_inject_block({"content": "昨天：\n\n今天："}, trigger)
    background = du_daily.build_background_prompt(trigger)
    assert events[0] in inject and events[-1] in inject
    assert events[0] in background and events[-1] in background

    captured_state: dict = {}
    original_get_state = du_daily.get_prepared_state
    original_save = du_daily.r2_store.save_du_daily_state
    try:
        du_daily.get_prepared_state = lambda: (
            {
                "day": "2026-07-28",
                "yesterday_summary": "",
                "today_summary": "",
                "today_events": [],
                "today_timeline": [],
            },
            False,
        )

        def fake_save(state):
            captured_state.update(state)
            return True

        du_daily.r2_store.save_du_daily_state = fake_save
        raw_block = "\n".join(f"新增：{event}" for event in events)
        assert du_daily.save_hidden_block(raw_block, trigger)
    finally:
        du_daily.get_prepared_state = original_get_state
        du_daily.r2_store.save_du_daily_state = original_save

    assert captured_state["today_events"] == events


def test_notebook_and_summary_injection_keep_full_content() -> None:
    notebook_entries = [{"content": f"记事本第{index}条-" + ("内容" * 100)} for index in range(25)]
    original_get_notebook = pipeline.r2_store.get_du_notebook_entries
    try:
        pipeline.r2_store.get_du_notebook_entries = lambda: notebook_entries
        body = pipeline.step_inject_du_notebook({"messages": [{"role": "user", "content": "测试"}]})
    finally:
        pipeline.r2_store.get_du_notebook_entries = original_get_notebook

    notebook_text = "\n".join(
        str(message.get("content") or "")
        for message in body["messages"]
        if message.get("role") == "system"
    )
    assert notebook_entries[0]["content"] in notebook_text
    assert notebook_entries[-1]["content"] in notebook_text

    long_recent = "最近正文" * 1200
    long_older = "更早正文" * 1200
    summary = f"【最近】\n{long_recent}\n\n【更早】\n{long_older}"
    original_get_summary = pipeline.r2_store.get_summary
    try:
        pipeline.r2_store.get_summary = lambda _window_id: summary
        body = pipeline.step_inject_summary({"messages": []}, "test-window")
    finally:
        pipeline.r2_store.get_summary = original_get_summary

    injected_text = "\n".join(str(message.get("content") or "") for message in body["messages"])
    assert long_recent in injected_text
    assert long_older in injected_text

    chunks_state = {
        "version": 2,
        "update_count": 1,
        "chunks": [
            {
                "id": "current:1-4",
                "sequence": 0,
                "level": "recent",
                "round_start": 1,
                "round_end": 4,
                "text": long_recent,
            }
        ],
    }
    rounds = [{"index": index, "timestamp": "2026-07-28T12:00:00+08:00"} for index in range(1, 5)]
    rendered = deepseek_summary.render_summary_from_chunks(chunks_state)
    updated, _state = deepseek_summary.build_pending_summary_update("", rounds, chunks_state)
    assert updated == rendered
    assert long_recent in updated


def test_summary_gap_recovery_processes_every_missing_group() -> None:
    chunks_state = {
        "version": 2,
        "chunks": [
            {
                "id": "current:1-4",
                "round_start": 1,
                "round_end": 4,
                "sequence": 0,
                "level": "recent",
                "text": "已有总结",
            }
        ],
    }
    calls: list[tuple[int, int]] = []
    original_every = pipeline.SUMMARY_EVERY_N_ROUNDS
    original_read = pipeline._summary_read_round_group
    try:
        pipeline.SUMMARY_EVERY_N_ROUNDS = 4

        def fake_read(_window_id: str, start: int, end: int):
            calls.append((start, end))
            return [{"index": index} for index in range(start, end + 1)]

        pipeline._summary_read_round_group = fake_read
        groups = pipeline._summary_round_groups_to_process("test-window", 40, chunks_state)
    finally:
        pipeline.SUMMARY_EVERY_N_ROUNDS = original_every
        pipeline._summary_read_round_group = original_read

    expected = [(start, start + 3) for start in range(5, 41, 4)]
    assert calls == expected
    assert len(groups) == len(expected)


def main() -> None:
    test_dynamic_query_and_embedding_keep_full_text()
    test_du_daily_keeps_all_events_and_full_text()
    test_notebook_and_summary_injection_keep_full_content()
    test_summary_gap_recovery_processes_every_missing_group()
    print("overtruncation removal self-check OK")


if __name__ == "__main__":
    main()
