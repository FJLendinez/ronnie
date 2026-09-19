"""Security headers middleware — equivalent of ``django.middleware.security``."""

from __future__ import annotations

import re
from typing import Any

__all__ = ["SecurityMiddleware", "_settings"]


def _settings() -> Any:
    from ..conf import settings

    return settings


def _header_value(message: dict[str, Any], name: bytes) -> bytes | None:
    for key, value in message.get("headers", []):
        if key.lower() == name:
            return bytes(value)
    return None


def _set_header(message: dict[str, Any], name: bytes, value: bytes) -> None:
    headers = list(message.get("headers", []))
    headers.append((name, value))
    message["headers"] = headers


class SecurityMiddleware:
    """Adds security headers to responses and optionally enforces HTTPS."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if redirect := self._ssl_redirect(scope):
            from starlette.responses import RedirectResponse

            await RedirectResponse(redirect, status_code=301)(scope, receive, send)
            return

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                self._patch_headers(scope, message)
            await send(message)

        await self.app(scope, receive, send_with_headers)

    # -- https redirect ---------------------------------------------------------

    def _ssl_redirect(self, scope: dict[str, Any]) -> str | None:
        s = _settings()
        if not s.SECURE_SSL_REDIRECT:
            return None
        scheme = scope.get("scheme", "http")
        header, expected = getattr(s, "SECURE_PROXY_SSL_HEADER", None) or (None, None)
        if header:
            for key, value in scope.get("headers", []):
                if key.decode().lower() == header.lower() and value.decode() == expected:
                    scheme = "https"
        if scheme == "https":
            return None
        path = scope.get("path", "/")
        for pattern in getattr(s, "SECURE_REDIRECT_EXEMPT", None) or []:
            if re.search(pattern, path):
                return None
        if query := scope.get("query_string", b"").decode():
            path += f"?{query}"
        host = self._host(scope, s)
        return f"https://{host}{path}"

    @staticmethod
    def _host(scope: dict[str, Any], s: Any) -> str:
        if ssl_host := getattr(s, "SECURE_SSL_HOST", None):
            return str(ssl_host)
        for key, value in scope.get("headers", []):
            if key == b"host":
                return str(value.decode())
        return str(scope.get("server", ("", ""))[0] or "localhost")

    # -- headers ------------------------------------------------------------------

    def _patch_headers(self, scope: dict[str, Any], message: dict[str, Any]) -> None:
        s = _settings()
        hsts_seconds = s.SECURE_HSTS_SECONDS
        if hsts_seconds and _header_value(message, b"strict-transport-security") is None:
            value = f"max-age={hsts_seconds}"
            if s.SECURE_HSTS_INCLUDE_SUBDOMAINS:
                value += "; includeSubDomains"
            if s.SECURE_HSTS_PRELOAD:
                value += "; preload"
            _set_header(message, b"strict-transport-security", value.encode())

        if s.SECURE_REFERRER_POLICY and _header_value(message, b"referrer-policy") is None:
            _set_header(message, b"referrer-policy", s.SECURE_REFERRER_POLICY.encode())

        coop = s.SECURE_CROSS_ORIGIN_OPENER_POLICY
        if coop and _header_value(message, b"cross-origin-opener-policy") is None:
            _set_header(message, b"cross-origin-opener-policy", coop.encode())

        if s.SECURE_CONTENT_TYPE_NOSNIFF and _header_value(message, b"x-content-type-options") is None:
            _set_header(message, b"x-content-type-options", b"nosniff")
