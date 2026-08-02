from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _tool_names(tools: list[dict]) -> set[str]:
    return {
        str((tool.get("function") or {}).get("name") or "")
        for tool in tools
        if isinstance(tool, dict)
    }


def test_default_chat_tools_hide_forum_without_hiding_other_tools() -> None:
    from services import mcp_forum_tools

    old_enabled = mcp_forum_tools.MCP_ENABLED
    old_forum_enabled = mcp_forum_tools.forum_mcp_enabled
    try:
        mcp_forum_tools.MCP_ENABLED = True
        mcp_forum_tools.forum_mcp_enabled = lambda: True
        chat_names = _tool_names(mcp_forum_tools.get_forum_tools_for_inject())
        explicit_forum_names = _tool_names(mcp_forum_tools.get_forum_tools_for_inject(mode="forum"))
    finally:
        mcp_forum_tools.MCP_ENABLED = old_enabled
        mcp_forum_tools.forum_mcp_enabled = old_forum_enabled

    hidden = {"forum_read_feed", "forum_open_thread", "cli", "get_guide"}
    assert not hidden.intersection(chat_names), chat_names
    assert {"open_app", "create_calendar_event", "search_memory"}.issubset(chat_names), chat_names
    assert hidden.issubset(explicit_forum_names), explicit_forum_names


def test_pipeline_chat_request_uses_the_hidden_forum_surface() -> None:
    import config
    from pipeline import pipeline
    from services import mcp_forum_tools

    old_config_enabled = config.MCP_ENABLED
    old_module_enabled = mcp_forum_tools.MCP_ENABLED
    old_forum_enabled = mcp_forum_tools.forum_mcp_enabled
    try:
        config.MCP_ENABLED = True
        mcp_forum_tools.MCP_ENABLED = True
        mcp_forum_tools.forum_mcp_enabled = lambda: True
        body = pipeline.step_inject_forum_tools(
            {
                "messages": [{"role": "user", "content": "test"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "existing_tool",
                            "description": "existing",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            }
        )
    finally:
        config.MCP_ENABLED = old_config_enabled
        mcp_forum_tools.MCP_ENABLED = old_module_enabled
        mcp_forum_tools.forum_mcp_enabled = old_forum_enabled

    names = _tool_names(body.get("tools") or [])
    assert not {"forum_read_feed", "forum_open_thread", "cli", "get_guide"}.intersection(names), names
    assert {"existing_tool", "open_app", "search_memory"}.issubset(names), names


def test_managed_old_wakeup_template_no_longer_offers_forum() -> None:
    from services import prompt_manager
    from services import telegram_proactive

    old_get = prompt_manager.get_managed_prompt_text
    try:
        prompt_manager.get_managed_prompt_text = lambda *_args, **_kwargs: (
            "可以选：给她发消息、暂时不打扰、去写日记/记事、逛论坛、上网冲浪找点可聊话题。\n"
            '{"action":"send_message|no_contact|diary|forum|surf|drawer|game|other"}'
        )
        rendered = telegram_proactive._render_random_proactive_decision_prompt(
            recent_exchange="最近没有新消息。",
            hours_since_last=1.0,
            channel_field_desc='- channel：固定填 "qq"。',
            default_channel="qq",
            no_contact_token="NO_CONTACT",
        )
    finally:
        prompt_manager.get_managed_prompt_text = old_get

    assert "逛论坛" not in rendered, rendered
    assert "forum" not in rendered, rendered
    assert "写日记" in rendered and "surf" in rendered, rendered


def test_after_surf_wakeup_prompt_no_longer_offers_forum() -> None:
    from services import telegram_proactive

    captured: dict = {}
    old_available = telegram_proactive._available_channels
    old_preferred = telegram_proactive._preferred_proactive_channel
    old_recent = telegram_proactive._describe_recent_exchange
    old_post = telegram_proactive.requests.post

    class _Response:
        status_code = 200
        content = b"{}"
        text = ""

        @staticmethod
        def json() -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "no_contact",
                                    "reason": "先不打扰",
                                    "message": "",
                                    "channel": "qq",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

    def fake_post(_url, *, headers, json, timeout):
        captured["headers"] = headers
        captured["body"] = json
        captured["timeout"] = timeout
        return _Response()

    try:
        telegram_proactive._available_channels = lambda: ["qq"]
        telegram_proactive._preferred_proactive_channel = lambda _channels: "qq"
        telegram_proactive._describe_recent_exchange = lambda _now: "最近没有新消息。"
        telegram_proactive.requests.post = fake_post
        decision = telegram_proactive._ask_du_after_surf_result(
            window_id="forum_hidden_test",
            hours_since_last=1.0,
            surf_result={"cards_for_du": []},
            initial_reason="随便看看",
        )
    finally:
        telegram_proactive._available_channels = old_available
        telegram_proactive._preferred_proactive_channel = old_preferred
        telegram_proactive._describe_recent_exchange = old_recent
        telegram_proactive.requests.post = old_post

    prompt = str((((captured.get("body") or {}).get("messages") or [{}])[0]).get("content") or "")
    assert decision.action == "no_contact", decision
    assert "forum" not in prompt, prompt
    assert '"diary"' in prompt and '"drawer"' in prompt and '"game"' in prompt, prompt


if __name__ == "__main__":
    test_default_chat_tools_hide_forum_without_hiding_other_tools()
    test_pipeline_chat_request_uses_the_hidden_forum_surface()
    test_managed_old_wakeup_template_no_longer_offers_forum()
    test_after_surf_wakeup_prompt_no_longer_offers_forum()
    print("hidden forum surface tests ok")
