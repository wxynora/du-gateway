import ipaddress

from flask import abort, request

from config import (
    MCP_AUTH_MODE,
    MCP_IP_ALLOWLIST,
    MCP_TOKENS,
    MCP_TRUST_PROXY,
)


def _get_client_ip() -> str:
    if MCP_TRUST_PROXY:
        xff = (request.headers.get("X-Forwarded-For") or "").strip()
        if xff:
            ip = xff.split(",")[0].strip()
            if ip:
                return ip
    return (request.remote_addr or "").strip()


def _parse_networks(items: list[str]):
    nets = []
    for s in items or []:
        s = (s or "").strip()
        if not s:
            continue
        try:
            if "/" in s:
                nets.append(ipaddress.ip_network(s, strict=False))
            else:
                ip = ipaddress.ip_address(s)
                nets.append(ipaddress.ip_network(f"{ip}/{ip.max_prefixlen}", strict=False))
        except Exception:
            # 单项写错时忽略，避免把服务锁死
            continue
    return nets


_ALLOW_NETS = None


def _extract_token() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-MCP-Token") or "").strip()


def _enforce_token():
    token = _extract_token()
    if not MCP_TOKENS:
        abort(401, description="MCP token 未配置")
    if not token or token not in set(MCP_TOKENS):
        abort(401, description="MCP token 无效")


def _enforce_ip_allowlist():
    global _ALLOW_NETS
    if not MCP_IP_ALLOWLIST:
        abort(403, description="MCP IP 白名单未配置")
    if _ALLOW_NETS is None:
        _ALLOW_NETS = _parse_networks(MCP_IP_ALLOWLIST)
    ip_str = _get_client_ip()
    if not ip_str:
        abort(403, description="无法获取客户端 IP")
    try:
        ip = ipaddress.ip_address(ip_str)
    except Exception:
        abort(403, description="客户端 IP 非法")
        return

    for net in _ALLOW_NETS or []:
        if ip in net:
            return
    abort(403, description="IP 不在 MCP 白名单")


def enforce_mcp_auth():
    """
    MCP 鉴权入口：
    - token：仅 token
    - token_ip：token + IP 白名单
    - off：不校验（仅调试）
    """
    if MCP_AUTH_MODE == "off":
        return
    _enforce_token()
    if MCP_AUTH_MODE == "token_ip":
        _enforce_ip_allowlist()
