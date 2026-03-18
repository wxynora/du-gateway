import ipaddress

from flask import abort, request

from config import MINIAPP_IP_ALLOWLIST, MINIAPP_TRUST_PROXY


def _get_client_ip() -> str:
    if MINIAPP_TRUST_PROXY:
        # X-Forwarded-For: client, proxy1, proxy2
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
                # 单 IP
                ip = ipaddress.ip_address(s)
                nets.append(ipaddress.ip_network(f"{ip}/{ip.max_prefixlen}", strict=False))
        except Exception:
            # 配置写错直接忽略该项，避免把自己锁死
            continue
    return nets


_ALLOW_NETS = None


def enforce_ip_allowlist():
    """用于 /miniapp-api/*：只允许白名单 IP 访问。"""
    global _ALLOW_NETS
    if not MINIAPP_IP_ALLOWLIST:
        return
    if _ALLOW_NETS is None:
        _ALLOW_NETS = _parse_networks(MINIAPP_IP_ALLOWLIST)
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
    abort(403, description="IP 不在白名单")

