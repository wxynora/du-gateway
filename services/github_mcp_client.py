"""Minimal client for GitHub's official hosted MCP server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from config import GITHUB_MCP_URL, GITHUB_PUBLIC_REPO_TOKEN, PUBLIC_REPO_TIMEOUT_SECONDS


_T = TypeVar("_T")
_ALLOWED_TOOLS = {
    "get_commit",
    "get_file_contents",
    "get_repository_tree",
    "search_code",
    "search_repositories",
}
_TOOLS_HEADER = ",".join(sorted(_ALLOWED_TOOLS))


class GitHubMcpError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.stage = stage


class _CallbackRaised(Exception):
    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _extract_attr(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value.get(name)
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _content_text(item: Any) -> str:
    raw = _model_dump(item)
    if isinstance(raw, dict):
        if str(raw.get("type") or "").strip().lower() == "text":
            return str(raw.get("text") or "").strip()
        try:
            return json.dumps(raw, ensure_ascii=False)
        except Exception:
            return str(raw)
    text = _extract_attr(item, "text")
    return str(text if text is not None else item or "").strip()


def _normalize_result(result: Any, tool_name: str) -> dict[str, Any]:
    raw = _model_dump(result)
    if not isinstance(raw, dict):
        raw = {}
    content_items = _extract_attr(result, "content") or raw.get("content") or []
    if not isinstance(content_items, list):
        content_items = [content_items]
    content_blocks = []
    for item in content_items:
        block = _model_dump(item)
        if isinstance(block, dict):
            content_blocks.append(block)
    content = "\n".join(part for part in (_content_text(item) for item in content_items) if part).strip()
    structured = _extract_attr(result, "structuredContent", "structured_content")
    if structured is None:
        structured = raw.get("structuredContent", raw.get("structured_content"))
    is_error = bool(
        _extract_attr(result, "isError", "is_error")
        or raw.get("isError")
        or raw.get("is_error")
    )
    return {
        "ok": not is_error,
        "tool": tool_name,
        "content": content,
        "content_blocks": content_blocks,
        "structured_content": structured,
        "source": "github_official_mcp",
    }


def _headers() -> dict[str, str]:
    token = str(GITHUB_PUBLIC_REPO_TOKEN or "").strip()
    if not token:
        raise GitHubMcpError("missing_token", "GitHub 官方 MCP 需要配置 GitHub token")
    return {
        "Authorization": f"Bearer {token}",
        "X-MCP-Readonly": "true",
        "X-MCP-Tools": _TOOLS_HEADER,
    }


def _exception_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    for value in (
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
        getattr(response, "status_code", None),
        getattr(response, "status", None),
    ):
        try:
            status = int(value)
        except (TypeError, ValueError):
            continue
        if 100 <= status <= 599:
            return status
    return None


def _translate_exception(exc: Exception, *, stage: str) -> GitHubMcpError:
    if isinstance(exc, GitHubMcpError):
        return exc
    if isinstance(exc, TimeoutError):
        return GitHubMcpError(
            "github_mcp_timeout",
            "GitHub 官方 MCP 请求超时",
            stage=stage,
        )

    status = _exception_status(exc)
    if status == 401:
        return GitHubMcpError(
            "github_mcp_auth_failed",
            "GitHub 官方 MCP 鉴权失败（HTTP 401）",
            status=status,
            stage=stage,
        )
    if status == 403:
        return GitHubMcpError(
            "github_mcp_access_denied",
            "GitHub 官方 MCP 拒绝访问（HTTP 403）",
            status=status,
            stage=stage,
        )
    if status == 404:
        return GitHubMcpError(
            "github_mcp_not_found",
            "GitHub 官方 MCP 地址或资源不存在（HTTP 404）",
            status=status,
            stage=stage,
        )
    if status == 429:
        return GitHubMcpError(
            "github_mcp_rate_limited",
            "GitHub 官方 MCP 已限流（HTTP 429）",
            status=status,
            stage=stage,
        )
    if status is not None and status >= 500:
        return GitHubMcpError(
            "github_mcp_upstream_unavailable",
            f"GitHub 官方 MCP 服务暂时不可用（HTTP {status}）",
            status=status,
            stage=stage,
        )
    if status is not None:
        return GitHubMcpError(
            "github_mcp_http_error",
            f"GitHub 官方 MCP 请求失败（HTTP {status}）",
            status=status,
            stage=stage,
        )

    error_type = type(exc).__name__ or "Exception"
    if isinstance(exc, OSError):
        return GitHubMcpError(
            "github_mcp_connection_failed",
            f"GitHub 官方 MCP 连接失败（{error_type}）",
            stage=stage,
        )
    return GitHubMcpError(
        "github_mcp_request_failed",
        f"GitHub 官方 MCP 请求失败（{error_type}）",
        stage=stage,
    )


async def _with_session_async(callback: Callable[[ClientSession], Awaitable[_T]]) -> _T:
    url = str(GITHUB_MCP_URL or "").strip()
    if not url:
        raise GitHubMcpError("missing_mcp_url", "未配置 GitHub 官方 MCP 地址")
    timeout = max(2, int(PUBLIC_REPO_TIMEOUT_SECONDS or 15))
    try:
        async with streamablehttp_client(
            url,
            headers=_headers(),
            timeout=timeout,
            sse_read_timeout=timeout,
        ) as streams:
            read_stream, write_stream, _get_session_id = streams
            async with ClientSession(read_stream, write_stream) as session:
                try:
                    await asyncio.wait_for(session.initialize(), timeout=timeout)
                except Exception as exc:
                    raise _translate_exception(exc, stage="initialize") from exc
                try:
                    return await callback(session)
                except GitHubMcpError:
                    raise
                except Exception as exc:
                    raise _CallbackRaised(exc) from exc
    except _CallbackRaised as exc:
        raise exc.original
    except GitHubMcpError:
        raise
    except Exception as exc:
        raise _translate_exception(exc, stage="transport") from exc


def run_in_session(callback: Callable[[ClientSession], Awaitable[_T]]) -> _T:
    return asyncio.run(_with_session_async(callback))


async def call_tool_with_session(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(tool_name or "").strip()
    if name not in _ALLOWED_TOOLS:
        raise GitHubMcpError("github_mcp_tool_forbidden", "该 GitHub MCP 工具未获准调用")
    timeout = max(2, int(PUBLIC_REPO_TIMEOUT_SECONDS or 15))
    try:
        result = await asyncio.wait_for(session.call_tool(name, arguments or {}), timeout=timeout)
    except GitHubMcpError:
        raise
    except Exception as exc:
        raise _translate_exception(exc, stage="tool_call") from exc
    return _normalize_result(result, name)


async def _call_tool_async(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(tool_name or "").strip()
    if name not in _ALLOWED_TOOLS:
        raise GitHubMcpError("github_mcp_tool_forbidden", "该 GitHub MCP 工具未获准调用")

    async def _callback(session: ClientSession) -> dict[str, Any]:
        return await call_tool_with_session(session, name, arguments)

    return await _with_session_async(_callback)


def call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    name = str(tool_name or "").strip()
    if name not in _ALLOWED_TOOLS:
        raise GitHubMcpError("github_mcp_tool_forbidden", "该 GitHub MCP 工具未获准调用")
    return asyncio.run(_call_tool_async(name, arguments or {}))
