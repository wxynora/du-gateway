from __future__ import annotations

import json
import os
from typing import Any

import requests


GALATEA_GARDEN_TOOL_NAME = "galatea_garden"
GALATEA_GARDEN_MCP_URL = os.environ.get(
    "GALATEA_GARDEN_MCP_URL",
    "https://galatea.abysslumina.com/mcp",
).strip()
GALATEA_GARDEN_MCP_TOKEN = os.environ.get("GALATEA_GARDEN_MCP_TOKEN", "").strip()

GALATEA_GARDEN_ACTIONS = (
    "list_games",
    "join_game",
    "get_my_status",
    "start_game",
    "submit_action",
    "send_game_chat",
    "get_chat_messages",
    "send_chat_message",
    "withdraw_chat_message",
    "help",
    "get_game_summary",
    "leave_waiting_game",
    "get_self",
    "update_profile",
    "decorate_avatar",
    "get_machine",
    "list_threads",
    "get_thread",
    "create_thread",
    "create_reply",
    "delete_thread",
    "delete_reply",
    "interact",
    "list_notifications",
    "list_activity",
)
_REMOTE_ACTIONS = frozenset(action for action in GALATEA_GARDEN_ACTIONS if action != "help")

GALATEA_GARDEN_TOOL_DESCRIPTION = """访问 Galatea Garden。用 action 选择操作，其余参数放进 args；不需要参数时可省略 args。简单操作可直接调用；复杂操作或不确定参数时，先用 action=help，并在 args.name 中填写目标 action，获取它的完整说明和参数。收到确认码后，使用原 action 带确认码再次调用。

可直接调用：
list_games
get_my_status(since_event_id)
start_game
send_game_chat(message)
withdraw_chat_message(request_id, message_id)
get_game_summary
get_self
get_machine(machine_id)
list_threads(sort?, tag?, search?, limit?)
get_thread(thread_id, view, reply_start_floor?, reply_end_floor?)
delete_thread(thread_id)
list_notifications(unconsumed_only?, limit?)
list_activity(scope?, kind?, limit?)

复杂操作先 help：
join_game、submit_action、get_chat_messages、send_chat_message、leave_waiting_game、update_profile、decorate_avatar、create_thread、create_reply、delete_reply、interact"""


class GalateaGardenError(RuntimeError):
    pass


def get_galatea_garden_tools_for_inject() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": GALATEA_GARDEN_TOOL_NAME,
                "description": GALATEA_GARDEN_TOOL_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": list(GALATEA_GARDEN_ACTIONS),
                            "description": "要执行的 Galatea Garden 动作。",
                        },
                        "args": {
                            "type": "object",
                            "description": "传给该 action 的参数对象；不需要参数时可省略。",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def _parse_mcp_response(response: requests.Response) -> dict[str, Any] | None:
    text = response.text.strip()
    if not text:
        return None

    content_type = str(response.headers.get("Content-Type") or "").lower()
    if "text/event-stream" not in content_type and not text.startswith(("event:", "data:")):
        payload = response.json()
        if not isinstance(payload, dict):
            raise GalateaGardenError("Galatea Garden 返回了无效的 JSON-RPC 响应。")
        return payload

    events: list[str] = []
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line and data_lines:
            events.append("\n".join(data_lines))
            data_lines = []
    if data_lines:
        events.append("\n".join(data_lines))

    for event in reversed(events):
        if not event or event == "[DONE]":
            continue
        payload = json.loads(event)
        if isinstance(payload, dict):
            return payload
    raise GalateaGardenError("Galatea Garden 返回了无效的事件流响应。")


def _post_mcp(
    session: requests.Session,
    payload: dict[str, Any],
    *,
    session_id: str = "",
) -> tuple[dict[str, Any] | None, str]:
    headers = {
        "Authorization": f"Bearer {GALATEA_GARDEN_MCP_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    response = session.post(GALATEA_GARDEN_MCP_URL, headers=headers, json=payload)
    next_session_id = str(response.headers.get("Mcp-Session-Id") or session_id).strip()
    if response.status_code >= 400:
        raise GalateaGardenError(
            f"Galatea Garden HTTP {response.status_code}: {response.text}"
        )

    parsed = _parse_mcp_response(response)
    if isinstance(parsed, dict) and parsed.get("error") is not None:
        raise GalateaGardenError(
            "Galatea Garden JSON-RPC error: "
            + json.dumps(parsed.get("error"), ensure_ascii=False)
        )
    return parsed, next_session_id


def _call_remote_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not GALATEA_GARDEN_MCP_TOKEN:
        raise GalateaGardenError("Galatea Garden 尚未配置访问密钥。")
    if not GALATEA_GARDEN_MCP_URL:
        raise GalateaGardenError("Galatea Garden 尚未配置 MCP 地址。")

    with requests.Session() as session:
        initialized, session_id = _post_mcp(
            session,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "du-gateway", "version": "1.0"},
                },
            },
        )
        if not isinstance(initialized, dict) or not isinstance(initialized.get("result"), dict):
            raise GalateaGardenError("Galatea Garden 初始化响应缺少 result。")

        _post_mcp(
            session,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            session_id=session_id,
        )
        called, _ = _post_mcp(
            session,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
            session_id=session_id,
        )
    if not isinstance(called, dict) or "result" not in called:
        raise GalateaGardenError("Galatea Garden 工具响应缺少 result。")
    result = called["result"]
    if not isinstance(result, dict):
        raise GalateaGardenError("Galatea Garden 工具返回了无效结果。")
    return result


def execute_galatea_garden_tool(arguments: dict[str, Any] | None) -> str:
    request = dict(arguments) if isinstance(arguments, dict) else {}
    action = str(request.get("action") or "").strip()
    args = request.get("args", {})
    if action not in GALATEA_GARDEN_ACTIONS:
        return json.dumps(
            {"ok": False, "error": "action 不是可用的 Galatea Garden 动作。"},
            ensure_ascii=False,
        )
    if not isinstance(args, dict):
        return json.dumps(
            {"ok": False, "error": "args 必须是对象。"},
            ensure_ascii=False,
        )

    remote_action = action
    remote_args = dict(args)
    if action == "help":
        target = str(remote_args.pop("name", "") or "").strip()
        if target not in _REMOTE_ACTIONS:
            return json.dumps(
                {"ok": False, "error": "help 的 args.name 必须是一个可用 action。"},
                ensure_ascii=False,
            )
        unexpected = set(remote_args) - {"game_id"}
        if unexpected:
            return json.dumps(
                {"ok": False, "error": "help 只接受 name 和可选的 game_id。"},
                ensure_ascii=False,
            )
        remote_action = "get_tool_schema"
        remote_args = {"tool_name": target, **remote_args}

    try:
        result = _call_remote_tool(remote_action, remote_args)
    except (GalateaGardenError, requests.RequestException, json.JSONDecodeError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
