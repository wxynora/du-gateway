from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import TRAVEL_MCP_HOME, TRAVEL_MCP_SCRIPT
from utils.log import get_logger


logger = get_logger(__name__)


class TravelMcpUnavailable(RuntimeError):
    pass


def travel_mcp_enabled() -> bool:
    return bool(TRAVEL_MCP_SCRIPT and TRAVEL_MCP_SCRIPT.is_file())


def _server_parameters() -> StdioServerParameters:
    script = TRAVEL_MCP_SCRIPT
    if script is None or not script.is_file():
        raise TravelMcpUnavailable("TRAVEL_MCP_UNAVAILABLE")
    env = dict(os.environ)
    env["TRAVEL_HOME"] = str(TRAVEL_MCP_HOME)
    env.pop("TRAVEL_HTTP", None)
    return StdioServerParameters(
        command=sys.executable,
        args=[str(script)],
        env=env,
        cwd=str(script.parent),
    )


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _content_text(item: Any) -> str:
    raw = _model_dump(item)
    if isinstance(raw, dict) and str(raw.get("type") or "").strip().lower() == "text":
        return str(raw.get("text") or "")
    text = getattr(item, "text", None)
    return str(text or "")


async def _call_tool_async(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    server = _server_parameters()
    async with stdio_client(server) as streams:
        read_stream, write_stream = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
    raw = _model_dump(result)
    content_items = getattr(result, "content", None)
    if content_items is None and isinstance(raw, dict):
        content_items = raw.get("content")
    if not isinstance(content_items, list):
        content_items = [content_items] if content_items is not None else []
    text = "\n".join(part for part in (_content_text(item) for item in content_items) if part).strip()
    is_error = bool(
        getattr(result, "isError", False)
        or getattr(result, "is_error", False)
        or (raw.get("isError") if isinstance(raw, dict) else False)
        or (raw.get("is_error") if isinstance(raw, dict) else False)
    )
    return {
        "ok": not is_error,
        "tool": tool_name,
        "arguments": arguments,
        "content": text,
        "content_items": [_model_dump(item) for item in content_items],
    }


def call_travel_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    logger.info("travel_mcp call tool=%s", tool_name)
    return asyncio.run(_call_tool_async(str(tool_name or "").strip(), dict(arguments or {})))


def result_text(result: dict[str, Any]) -> str:
    text = str((result or {}).get("content") or "").strip()
    if text:
        return text
    return json.dumps(
        {
            "ok": bool((result or {}).get("ok")),
            "error": "TRAVEL_MCP_EMPTY_RESULT",
        },
        ensure_ascii=False,
    )
