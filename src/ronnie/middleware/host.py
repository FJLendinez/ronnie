"""Host-header validation — the ``ALLOWED_HOSTS`` check from Django.

Empty ``ALLOWED_HOSTS`` + ``DEBUG=True`` allows localhost variants and
``testserver`` (matching Django's behaviour); in production every host must
be listed explicitly. Patterns: ``sub.example.com`` exact, ``.example.com``
matches the domain and all subdomains, ``*`` matches anything (warned about
by ``ronnie check --deploy``).
"""

from __future__ import annotations

from typing import Any

__all__ = ["HostValidationMiddleware", "validate_host"]

_LOCALHOST_VARIANTS = {"localhost", "127.0.0.1", "[::1]", "testserver"}


def validate_host(host: str, allowed: list[str]) -> bool:
    host = (host or "").lower().rstrip(".")
    if ":" in host and not host.startswith("["):  # strip port (keep ipv6 brackets)
        host = host.rsplit(":", 1)[0]
    for pattern in allowed:
        pattern = pattern.lower().rstrip(".")
        if pattern == "*":
            return True
        if pattern.startswith(".") and (host == pattern[1:] or host.endswith(pattern)):
            return True
        if host == pattern:
            return True
    return False


def _allowed_hosts() -> list[str]:
    from ..conf import settings

    allowed = list(settings.ALLOWED_HOSTS)
    if not allowed and settings.DEBUG:
        return sorted(_LOCALHOST_VARIANTS)
    return allowed


class HostValidationMiddleware:
    """Reject requests whose Host header is not allowed (400 Bad Request)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict((k.decode().lower(), v.decode()) for k, v in scope.get("headers", []))
        host = headers.get("x-forwarded-host") if _use_forwarded() else None
        host = host or headers.get("host", "")

        allowed = _allowed_hosts()
        if allowed and not validate_host(host, allowed):
            from starlette.responses import PlainTextResponse

            await PlainTextResponse(
                f"Invalid HTTP_HOST header: {host!r}. You may need to add it to ALLOWED_HOSTS.",
                status_code=400,
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _use_forwarded() -> bool:
    from ..conf import settings

    return bool(getattr(settings, "USE_X_FORWARDED_HOST", False))
