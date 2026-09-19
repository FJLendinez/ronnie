"""RonnieTestClient — an ergonomic test client built on Starlette's TestClient.

Usage::

    from ronnie.testing import RonnieTestClient

    client = RonnieTestClient()
    response = client.get("/pages/")
    response = client.post("/save/", data={"title": "hi"})
    response = client.htmx("get", "/fragment/")

The ASGI application is built lazily on the first request, so settings can be
configured after the client is constructed (useful in pytest fixtures).
"""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

__all__ = ["RonnieTestClient"]


class RonnieTestClient:
    """HTTP client with cookies, HTMX helpers and redirect following."""

    def __init__(
        self,
        app: Any = None,
        *,
        base_url: str = "http://testserver",
        headers: dict[str, str] | None = None,
        follow_redirects: bool = False,
        raise_server_exceptions: bool = True,
    ) -> None:
        self._app = app
        self._opts: dict[str, Any] = {
            "base_url": base_url,
            "headers": headers,
            "follow_redirects": follow_redirects,
            "raise_server_exceptions": raise_server_exceptions,
        }
        self._client: TestClient | None = None

    @property
    def _tc(self) -> TestClient:
        if self._client is None:
            from ..conf import settings

            # Test requests use Host: testserver — allow it (Django parity).
            try:
                if "testserver" not in settings.ALLOWED_HOSTS:
                    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]
            except Exception:
                pass
            app = self._app
            if app is None:
                from ..core.asgi import get_asgi_application

                app = get_asgi_application()
            self._client = TestClient(app, **self._opts)
        return self._client

    # -- raw access -------------------------------------------------------------

    @property
    def cookies(self) -> Any:
        return self._tc.cookies

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._tc.request(method, path, **kwargs)

    # -- verbs ---------------------------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._tc.get(path, **kwargs)

    def post(self, path: str, data: Any = None, **kwargs: Any) -> Any:
        return self._tc.post(path, data=data, **kwargs)

    def put(self, path: str, data: Any = None, **kwargs: Any) -> Any:
        return self._tc.put(path, data=data, **kwargs)

    def patch(self, path: str, data: Any = None, **kwargs: Any) -> Any:
        return self._tc.patch(path, data=data, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._tc.delete(path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Any:
        return self._tc.head(path, **kwargs)

    # -- helpers ---------------------------------------------------------------------

    def htmx(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a request that looks like an HTMX request (HX-Request: true)."""
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("HX-Request", "true")
        return self.request(method.upper(), path, headers=headers, **kwargs)

    def json_request(self, method: str, path: str, payload: Any = None, **kwargs: Any) -> Any:
        """Send a JSON request and return the response."""
        return self.request(method.upper(), path, json=payload, **kwargs)
