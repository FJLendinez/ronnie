"""Session middleware mount — configures Starlette's signed-cookie sessions.

Ronnie places the session middleware inside its own ``MIDDLEWARE`` stack
(instead of FastHTML's internal slot) so middlewares listed *after* it —
CSRF, auth, messages — can read ``scope["session"]``. The pluggable engines
of ``ronnie.contrib.sessions`` (Fase 7) swap the class via ``SESSION_ENGINE``.
"""

from __future__ import annotations

from typing import Any

from starlette.middleware.sessions import SessionMiddleware as _StarletteSessionMiddleware

__all__ = ["SessionMiddleware", "is_session_middleware"]


class SessionMiddleware:
    """Wrap Starlette's SessionMiddleware with Ronnie's settings."""

    def __init__(self, app: Any) -> None:
        from ..conf import settings

        self._middleware = _StarletteSessionMiddleware(
            app,
            secret_key=settings.SECRET_KEY or "ronnie-insecure-ephemeral-key",
            session_cookie=settings.SESSION_COOKIE_NAME,
            max_age=settings.SESSION_COOKIE_AGE,
            same_site=settings.SESSION_COOKIE_SAMESITE,
            https_only=settings.SESSION_COOKIE_SECURE,
            domain=settings.SESSION_COOKIE_DOMAIN,
        )

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await self._middleware(scope, receive, send)


def is_session_middleware(middleware: Any) -> bool:
    """True if a resolved middleware entry provides ``scope['session']``."""
    cls = getattr(middleware, "cls", middleware)
    if cls is SessionMiddleware or cls is _StarletteSessionMiddleware:
        return True
    return isinstance(cls, type) and (
        issubclass(cls, SessionMiddleware) or issubclass(cls, _StarletteSessionMiddleware)
    )
