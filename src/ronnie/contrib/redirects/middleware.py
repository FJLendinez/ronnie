"""RedirectFallbackMiddleware: DB redirects kick in only on 404 (Django parity).

Place it LAST in ``MIDDLEWARE``. ``new_path`` empty → 410 Gone.
"""

from __future__ import annotations

from typing import Any

__all__ = ["RedirectFallbackMiddleware"]


class RedirectFallbackMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        takeover: dict[str, Any] = {}

        async def send_watch(message: dict[str, Any]) -> None:
            if takeover:
                return  # original 404 suppressed: we answer after the app ends
            if (
                message["type"] == "http.response.start"
                and message["status"] == 404
                and (redirect := self._lookup(scope.get("path", "/")))
            ):
                takeover["redirect"] = redirect
                return
            await send(message)

        await self.app(scope, receive, send_watch)

        if "redirect" in takeover:
            target, code = takeover["redirect"]
            headers = [(b"location", target.encode())] if target else []
            await send({"type": "http.response.start", "status": code, "headers": headers})
            await send({"type": "http.response.body", "body": b""})

    @staticmethod
    def _lookup(path: str) -> tuple[str, int] | None:
        try:
            from ...db import get_table
            from .models import RonnieRedirect

            row = get_table(RonnieRedirect, pk="old_path")[path]
        except Exception:
            return None
        code = int(row.response_code or 302)
        if not row.new_path:
            return ("", 410)
        return (row.new_path, code)
