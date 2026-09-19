"""Sample middleware for tests: adds an X-Ronnie header to every response."""


class XHeaderMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-ronnie", b"on"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)


def screaming_keys(key: str, prefix: str, version: int) -> str:
    """Custom cache key function for coverage tests."""
    return f"{prefix}|{version}|{key.upper()}"
