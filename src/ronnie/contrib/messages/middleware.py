"""Messages middleware: ships cookie-storage Set-Cookie headers on responses."""

from __future__ import annotations

from typing import Any

from .storage import PENDING_KEY

__all__ = ["MessagesMiddleware"]


class MessagesMiddleware:
    """Flush ``scope['ronnie.set_cookies']`` into Set-Cookie response headers."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_cookies(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start" and PENDING_KEY in scope:
                from .storage import COOKIE_NAME, Message, encode_cookie_payload

                pending = [m for m in scope[PENDING_KEY] if isinstance(m, (list, dict))]
                if pending:
                    messages = [m for m in (Message.from_list(r) for r in pending) if m]
                    cookie = f"{COOKIE_NAME}={encode_cookie_payload(messages)}"
                else:  # consumed during the request: expire the cookie
                    cookie = f"{COOKIE_NAME}=; Max-Age=0"
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", cookie.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cookies)
