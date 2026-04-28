from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any
from urllib.parse import quote

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from config import (
    AMAP_API_KEY,
    AMAP_MCP_TIMEOUT_SECONDS,
    AMAP_MCP_TOOLS_CACHE_SECONDS,
    AMAP_MCP_URL,
)
from utils.log import get_logger

logger = get_logger(__name__)

_TOOLS_CACHE_LOCK = threading.Lock()
_TOOLS_CACHE: dict[str, dict[str, Any]] = {}
_TOOLS_CACHE_AT = 0.0


def amap_mcp_enabled() -> bool:
    return bool((AMAP_MCP_URL or "").strip() or (AMAP_API_KEY or "").strip())


def _require_amap_mcp_url() -> str:
    url = (AMAP_MCP_URL or "").strip()
    if url:
        return url
    key = (AMAP_API_KEY or "").strip()
    if not key:
        raise RuntimeError("未配置 AMAP_API_KEY 或 AMAP_MCP_URL")
    return f"https://mcp.amap.com/mcp?key={quote(key, safe='')}"


def _run_async(coro):
    return asyncio.run(coro)


def _is_sse_url(url: str) -> bool:
    clean = str(url or "").split("?", 1)[0].rstrip("/").lower()
    return clean.endswith("/sse")


async def _with_session_async(callback, timeout_seconds: int | None = None):
    url = _require_amap_mcp_url()
    timeout = max(1, int(timeout_seconds or AMAP_MCP_TIMEOUT_SECONDS or 30))
    if _is_sse_url(url):
        async with sse_client(url) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                return await asyncio.wait_for(callback(session), timeout=timeout)

    async with streamablehttp_client(url, timeout=timeout, sse_read_timeout=timeout) as streams:
        read_stream, write_stream, _get_session_id = streams
        async with ClientSession(read_stream, write_stream) as session:
            await asyncio.wait_for(session.initialize(), timeout=timeout)
            return await asyncio.wait_for(callback(session), timeout=timeout)


def run_in_session(callback, timeout_seconds: int | None = None):
    if not amap_mcp_enabled():
        raise RuntimeError("未配置 AMAP_API_KEY 或 AMAP_MCP_URL")
    return _run_async(_with_session_async(callback, timeout_seconds=timeout_seconds))


def _model_dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _extract_attr(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj.get(name)
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _normalize_tool_meta(tool: Any) -> dict[str, Any]:
    raw = _model_dump(tool)
    if not isinstance(raw, dict):
        raw = {}
    name = _extract_attr(tool, "name") or raw.get("name") or ""
    description = _extract_attr(tool, "description") or raw.get("description") or ""
    input_schema = (
        _extract_attr(tool, "inputSchema", "input_schema")
        or raw.get("inputSchema")
        or raw.get("input_schema")
        or {}
    )
    return {
        "name": str(name).strip(),
        "description": str(description or "").strip(),
        "input_schema": input_schema if isinstance(input_schema, dict) else {},
    }


async def _list_tools_async() -> dict[str, dict[str, Any]]:
    async def _callback(session: ClientSession):
        result = await session.list_tools()
        tools = _extract_attr(result, "tools") or []
        out: dict[str, dict[str, Any]] = {}
        for tool in tools or []:
            meta = _normalize_tool_meta(tool)
            name = meta.get("name") or ""
            if name:
                out[name] = meta
        return out

    return await _with_session_async(_callback)


def list_tools(force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    global _TOOLS_CACHE, _TOOLS_CACHE_AT

    if not amap_mcp_enabled():
        return {}
    ttl = max(0, int(AMAP_MCP_TOOLS_CACHE_SECONDS or 0))
    now = time.time()
    with _TOOLS_CACHE_LOCK:
        if (not force_refresh) and _TOOLS_CACHE and ttl > 0 and (now - _TOOLS_CACHE_AT) < ttl:
            return dict(_TOOLS_CACHE)

    tools = _run_async(_list_tools_async())
    with _TOOLS_CACHE_LOCK:
        _TOOLS_CACHE = dict(tools)
        _TOOLS_CACHE_AT = time.time()
    return dict(tools)


def _flatten_content_item(item: Any) -> str:
    raw = _model_dump(item)
    if isinstance(raw, dict):
        kind = str(raw.get("type") or "").strip().lower()
        if kind == "text":
            return str(raw.get("text") or "").strip()
        if kind == "image":
            return "[image]"
        if kind:
            try:
                return json.dumps(raw, ensure_ascii=False)
            except Exception:
                return str(raw)
    text = _extract_attr(item, "text")
    if text is not None:
        return str(text).strip()
    return str(item or "").strip()


def _normalize_call_result(result: Any, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    raw = _model_dump(result)
    if not isinstance(raw, dict):
        raw = {}
    content_items = _extract_attr(result, "content") or raw.get("content") or []
    if not isinstance(content_items, list):
        content_items = [content_items]
    text_parts = [part for part in (_flatten_content_item(item) for item in content_items) if part]
    structured = _extract_attr(result, "structuredContent", "structured_content")
    if structured is None:
        structured = raw.get("structuredContent")
    is_error = bool(_extract_attr(result, "isError", "is_error") or raw.get("isError") or raw.get("is_error"))
    return {
        "ok": not is_error,
        "tool": tool_name,
        "arguments": arguments,
        "content": "\n".join(text_parts).strip(),
        "content_items": [_model_dump(item) for item in content_items],
        "structured_content": structured,
        "source": "amap_mcp",
    }


async def _call_tool_async(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async def _callback(session: ClientSession):
        return await call_tool_with_session(session, tool_name, arguments)

    return await _with_session_async(_callback)


async def call_tool_with_session(session: ClientSession, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    result = await session.call_tool(tool_name, args)
    return _normalize_call_result(result, tool_name, args)


def call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not amap_mcp_enabled():
        raise RuntimeError("未配置 AMAP_API_KEY 或 AMAP_MCP_URL")
    logger.info("amap_mcp call tool=%s", tool_name)
    return _run_async(_call_tool_async(tool_name, arguments or {}))
