"""Small header policy supplement to Starlette's trusted-host middleware.

No DNS, body reads, authentication state or proxy-header trust. Host allowlisting
itself remains with TrustedHostMiddleware in the existing ASGI wrapper.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any


LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
_AUTHORITY = re.compile(r"(\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::([0-9]{1,5}))?", re.I | re.ASCII)
_ORIGIN = re.compile(r"(https?)://(.+)", re.I | re.ASCII)


def _authority(value: str, scheme: str) -> tuple[str, str, int] | None:
    match = _AUTHORITY.fullmatch(value)
    if not match or scheme not in {"http", "https"}:
        return None
    host = match[1].lower()
    if host.startswith("["):
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            return None
    port = int(match[2]) if match[2] is not None else (443 if scheme == "https" else 80)
    return (scheme, host, port) if 1 <= port <= 65535 else None


def header_error(scope: dict[str, Any]) -> int | None:
    """Return a fixed rejection status, never an untrusted value for an error."""
    headers = scope.get("headers", [])

    def values(name: bytes) -> list[bytes]:
        return [value for key, value in headers if key.lower() == name]

    hosts = values(b"host")
    if len(hosts) != 1:
        return 400
    try:
        authority = _authority(hosts[0].decode("ascii"), scope.get("scheme", ""))
    except UnicodeError:
        return 400
    if authority is None:
        return 400

    origins = values(b"origin")
    if origins:
        if len(origins) != 1:
            return 403
        try:
            match = _ORIGIN.fullmatch(origins[0].decode("ascii"))
        except UnicodeError:
            return 403
        if not match or _authority(match[2], match[1].lower()) != authority:
            return 403

    sites = values(b"sec-fetch-site")
    if sites:
        if len(sites) != 1 or sites[0] not in {b"same-origin", b"same-site", b"cross-site", b"none"}:
            return 403
        path = scope.get("path", "")
        protected = any(path == prefix or path.startswith(prefix + "/") for prefix in ("/api", "/mcp"))
        if protected and sites[0] in {b"same-site", b"cross-site"}:
            return 403
    return None
