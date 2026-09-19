"""Engine-aware session middleware (Django's SESSION_ENGINE equivalent).

For the ``cookie`` engine it delegates to Starlette's signed-cookie
SessionMiddleware. Server-side engines (``db``, custom) load the session
dict into ``scope["session"]`` before the app runs and persist it afterwards
when modified — handlers keep receiving the same ``sess``/``session`` dict
either way.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

from starlette.middleware.sessions import SessionMiddleware as _StarletteSessionMiddleware

from ...conf import settings
from .engines import COOKIE_ENGINE, SessionEngine, resolve_engine

__all__ = ["SessionMiddleware", "TrackingSession", "is_session_middleware"]


class TrackingSession(dict[str, Any]):
    """A dict that records whether it was mutated (persist only on change)."""

    modified = False

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self.modified = True

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self.modified = True

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self.modified = True

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        result = super().pop(*args, **kwargs)
        self.modified = True
        return result

    def clear(self) -> None:
        super().clear()
        self.modified = True

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self:
            self.modified = True
        return super().setdefault(key, default)


class SessionMiddleware:
    """Configure sessions from settings; delegate to the selected engine."""

    def __init__(self, app: Any) -> None:
        resolved: str | SessionEngine = resolve_engine(settings.SESSION_ENGINE)
        if resolved == COOKIE_ENGINE:
            self._cookie_mw: Any = _StarletteSessionMiddleware(
                app,
                secret_key=settings.SECRET_KEY or "ronnie-insecure-ephemeral-key",
                session_cookie=settings.SESSION_COOKIE_NAME,
                max_age=settings.SESSION_COOKIE_AGE,
                same_site=settings.SESSION_COOKIE_SAMESITE,
                https_only=settings.SESSION_COOKIE_SECURE,
                domain=settings.SESSION_COOKIE_DOMAIN,
            )
            self._app: Any = None
            self._engine: SessionEngine | None = None
        else:
            self._cookie_mw = None
            self._app = app
            assert not isinstance(resolved, str)
            self._engine = resolved

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if self._cookie_mw is not None:
            await self._cookie_mw(scope, receive, send)
            return
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        await self._run_engine(scope, receive, send)

    # -- server-side engine flow ---------------------------------------------------

    async def _run_engine(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        assert self._engine is not None and self._app is not None
        engine = self._engine
        app = self._app
        cookie_name = settings.SESSION_COOKIE_NAME
        cookies = _parse_cookies(scope)
        session_key = cookies.get(cookie_name)

        data = engine.load(session_key) if session_key else None
        session = TrackingSession(data or {})
        scope["session"] = session

        async def send_with_persist(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if scope.get("ronnie.session_flush"):
                    if session_key:
                        engine.delete(session_key)
                    headers.append((b"set-cookie", _expire_cookie(cookie_name)))
                elif session.modified:
                    if session:
                        new_key = session_key or engine.new_key()
                        engine.save(new_key, dict(session), settings.SESSION_COOKIE_AGE)
                        headers.append((b"set-cookie", _set_cookie(cookie_name, new_key)))
                    elif session_key:  # emptied by the handler: drop it
                        engine.delete(session_key)
                        headers.append((b"set-cookie", _expire_cookie(cookie_name)))
                message["headers"] = headers
            await send(message)

        await app(scope, receive, send_with_persist)


def _parse_cookies(scope: dict[str, Any]) -> dict[str, str]:
    jar = SimpleCookie()
    for key, value in scope.get("headers", []):
        if key.decode().lower() == "cookie":
            jar.load(value.decode())
    return {k: m.value for k, m in jar.items()}


def _cookie_common() -> str:
    parts = ["Path=/", "HttpOnly", f"SameSite={settings.SESSION_COOKIE_SAMESITE or 'Lax'}"]
    if settings.SESSION_COOKIE_SECURE:
        parts.append("Secure")
    if settings.SESSION_COOKIE_DOMAIN:
        parts.append(f"Domain={settings.SESSION_COOKIE_DOMAIN}")
    return "; ".join(parts)


def _set_cookie(name: str, value: str) -> bytes:
    return (f"{name}={value}; Max-Age={settings.SESSION_COOKIE_AGE}; {_cookie_common()}").encode()


def _expire_cookie(name: str) -> bytes:
    return f"{name}=; Max-Age=0; {_cookie_common()}".encode()


def is_session_middleware(middleware: Any) -> bool:
    """True if a resolved middleware entry provides ``scope['session']``."""
    cls = getattr(middleware, "cls", middleware)
    if cls is SessionMiddleware or cls is _StarletteSessionMiddleware:
        return True
    return isinstance(cls, type) and (
        issubclass(cls, SessionMiddleware) or issubclass(cls, _StarletteSessionMiddleware)
    )
