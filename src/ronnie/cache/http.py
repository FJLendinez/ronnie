"""HTTP-side caching: per-view decorator, per-site middleware, fragments.

- ``cache_page(timeout)`` — cache a handler's rendered response for GETs.
- ``CacheMiddleware`` — per-site GET/HEAD 200 caching by URL.
- ``cache_fragment(name, timeout, builder)`` — cache rendered FT fragments.
- ``no_cache()`` / ``cache_control(**kw)`` — header helpers to include in
  handler return tuples (FastHTML ``HttpHeader`` style).
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from fasthtml.common import HttpHeader
from fasthtml.core import to_xml

from . import caches

__all__ = [
    "CacheMiddleware",
    "cache_control",
    "cache_fragment",
    "cache_page",
    "make_fragment_key",
    "no_cache",
]


def _request_of(kwargs: dict[str, Any]) -> Any:
    return kwargs.get("req") or kwargs.get("request")


def cache_page(timeout: int, *, cache: str = "default", key_prefix: str = "") -> Callable[[Any], Any]:
    """Cache a handler's rendered output for GET requests.

    The handler must accept ``req``/``request`` (for the URL); POSTs and
    other methods bypass the cache.
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = _request_of(kwargs)
            if request is None or request.method.upper() != "GET":
                return view(*args, **kwargs)
            query = dict(request.query_params)
            key = f"{key_prefix}:{request.url.path}:{sorted(query.items())}"
            backend = caches[cache]
            cached = backend.get(key)
            if cached is not None:
                return cached
            result = view(*args, **kwargs)
            if isinstance(result, str):
                backend.set(key, result, timeout)
            else:
                backend.set(key, to_xml(result), timeout)
            return result

        return wrapper

    return decorator


def make_fragment_key(fragment_name: str, vary_on: list[str] | None = None) -> str:
    return ":".join(["template.fragment", fragment_name, *(vary_on or [])])


def cache_fragment(key: str, timeout: int, builder: Callable[[], Any], *, cache: str = "default") -> str:
    """Render (and cache) an FT fragment; returns the cached XML string."""
    backend = caches[cache]
    cached = backend.get(key)
    if cached is not None:
        return str(cached)
    fresh = to_xml(builder())
    backend.set(key, fresh, timeout)
    return str(fresh)


def no_cache() -> Any:
    return HttpHeader("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")


def cache_control(**kwargs: Any) -> Any:
    """Build a Cache-Control header: ``cache_control(max_age=3600, private=True)``."""
    parts = []
    for name, value in kwargs.items():
        header = name.replace("_", "-")
        if value is True:
            parts.append(header)
        elif value is False or value is None:
            continue
        else:
            parts.append(f"{header}={value}")
    return HttpHeader("Cache-Control", ", ".join(parts))


class CacheMiddleware:
    """Per-site response cache for GET/HEAD 200s, keyed by method+path+query."""

    def __init__(self, app: Any) -> None:
        self.app = app
        from ..conf import settings

        self._alias = getattr(settings._wrapped, "CACHE_MIDDLEWARE_ALIAS", None) or "default"
        self._timeout = getattr(settings._wrapped, "CACHE_MIDDLEWARE_SECONDS", None) or 600
        self._key_prefix = str(getattr(settings._wrapped, "CACHE_MIDDLEWARE_KEY_PREFIX", None) or "")

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return

        query = scope.get("query_string", b"").decode()
        key = f"{self._key_prefix}:resp:{scope['method']}:{scope['path']}:{query}"
        backend = caches[self._alias]
        cached = backend.get(key)
        if cached is not None:
            status, headers, body = cached

            async def send_cached(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    message["status"] = status
                    message["headers"] = list(headers)
                    await send(message)
                elif message["type"] == "http.response.body":
                    if not message.get("more_body"):
                        await send({"type": "http.response.body", "body": body})
                else:  # pragma: no cover
                    await send(message)

            await send_cached({"type": "http.response.start"})
            await send_cached({"type": "http.response.body"})
            return

        state: dict[str, Any] = {"status": 200, "headers": [], "body": b""}

        async def send_collect(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                state["headers"] = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                state["body"] += message.get("body", b"")
            await send(message)

        await self.app(scope, receive, send_collect)
        if state["status"] == 200:
            backend.set(key, (state["status"], state["headers"], state["body"]), self._timeout)
