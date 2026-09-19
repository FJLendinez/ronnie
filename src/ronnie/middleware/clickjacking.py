"""Clickjacking protection — ``X-Frame-Options`` like Django's middleware."""

from __future__ import annotations

from typing import Any

__all__ = ["XFrameOptionsMiddleware"]


class XFrameOptionsMiddleware:
    """Set ``X-Frame-Options`` (default ``DENY``) unless already present."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-frame-options" for k, _ in headers):
                    from ..conf import settings

                    headers.append((b"x-frame-options", settings.X_FRAME_OPTIONS.upper().encode()))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)
