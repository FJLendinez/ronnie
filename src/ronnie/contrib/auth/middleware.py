"""Authentication middleware: ``scope["user"]`` + FastHTML's ``auth`` param."""

from __future__ import annotations

from typing import Any

__all__ = ["AuthMiddleware", "get_user_from_scope"]


class AuthMiddleware:
    """Attach the logged-in user (or AnonymousUser) to every request."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        user = get_user_from_scope(scope)
        scope["user"] = user
        # FastHTML handlers can request the special `auth` parameter.
        scope["auth"] = user if getattr(user, "is_authenticated", False) else None
        await self.app(scope, receive, send)


def get_user_from_scope(scope: dict[str, Any]) -> Any:
    """Resolve the user from the session in ``scope``, or AnonymousUser."""
    from .api import get_user
    from .models import AnonymousUser

    try:
        return get_user(scope)
    except Exception:
        return AnonymousUser()
