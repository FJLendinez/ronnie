"""Message storages (django.contrib.messages.storage equivalent).

- ``SessionStorage``: messages live in ``session["_messages"]``.
- ``CookieStorage``: signed cookie (payload cap ~2 KB, Django parity).
- ``FallbackStorage`` (default): cookie first, overflowing to the session.

Messages are cleared when consumed (``Alerts()`` / ``get_messages()``).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from ...core.signing import TimestampSigner, b64_encode

__all__ = [
    "COOKIE_NAME",
    "MAX_COOKIE_SIZE",
    "SESSION_KEY",
    "BaseStorage",
    "CookieStorage",
    "FallbackStorage",
    "Message",
    "SessionStorage",
]

SESSION_KEY = "_messages"
COOKIE_NAME = "ronnie_messages"
MAX_COOKIE_SIZE = 2048
PENDING_KEY = "ronnie.messages.cookie_pending"  # in-scope buffer for cookie storage


@dataclass
class Message:
    level: int
    message: str
    extra_tags: str = ""

    def as_list(self) -> list[Any]:
        return [self.level, self.message, self.extra_tags]

    @classmethod
    def from_list(cls, raw: Any) -> Message | None:
        if isinstance(raw, dict):
            return cls(int(raw.get("level", 20)), str(raw.get("message", "")), str(raw.get("extra_tags", "")))
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            return cls(int(raw[0]), str(raw[1]), str(raw[2]) if len(raw) > 2 else "")
        return None

    @property
    def level_tag(self) -> str:
        from ...conf import settings

        tags = dict(DEFAULT_TAGS)
        tags.update(getattr(settings._wrapped, "MESSAGE_TAGS", None) or {})
        return str(tags.get(self.level, ""))

    @property
    def tags(self) -> str:
        return " ".join(t for t in (self.extra_tags, self.level_tag) if t)


DEFAULT_TAGS = {10: "debug", 20: "info", 25: "success", 30: "warning", 40: "error"}


def _scope_of(request: Any) -> dict[str, Any]:
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):  # pragma: no cover - defensive
        raise TypeError("message storages expect a request object")
    return scope


def _session_of(scope: dict[str, Any]) -> dict[str, Any]:
    session = scope.get("session")
    if not isinstance(session, dict):
        from ...core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured("contrib.messages requires the session middleware.")
    return session


class BaseStorage:
    """Read/add messages; subclasses choose persistence."""

    def _load(self, scope: dict[str, Any]) -> list[Message]:
        raise NotImplementedError

    def _persist(self, scope: dict[str, Any], messages: list[Message]) -> None:
        raise NotImplementedError

    def _clear(self, scope: dict[str, Any]) -> None:
        raise NotImplementedError

    # -- public API (request-level) ------------------------------------------------

    def add(self, request: Any, level: int, message: str, extra_tags: str = "") -> None:
        from ...conf import settings

        if level < int(getattr(settings._wrapped, "MESSAGE_LEVEL", 20)):
            return  # below the minimum: drop silently (Django parity)
        messages = self._load(_scope_of(request))
        messages.append(Message(level, str(message), extra_tags))
        self._persist(_scope_of(request), messages)

    def read(self, request: Any, *, consume: bool = True) -> list[Message]:
        scope = _scope_of(request)
        messages = self._load(scope)
        if consume and messages:
            self._clear(scope)
        return messages


class SessionStorage(BaseStorage):
    def _load(self, scope: dict[str, Any]) -> list[Message]:
        session = _session_of(scope)
        raw = session.get(SESSION_KEY) or []
        return [m for m in (Message.from_list(r) for r in raw) if m is not None]

    def _persist(self, scope: dict[str, Any], messages: list[Message]) -> None:
        session = _session_of(scope)
        session[SESSION_KEY] = [m.as_list() for m in messages]

    def _clear(self, scope: dict[str, Any]) -> None:
        session = _session_of(scope)
        session.pop(SESSION_KEY, None)


def encode_cookie_payload(messages: list[Message]) -> str:
    """Serialize + sign messages for the cookie (validates the size cap)."""
    payload = json.dumps([m.as_list() for m in messages])
    signed = TimestampSigner(salt="ronnie.messages").sign(b64_encode(payload.encode()))
    if len(signed) > MAX_COOKIE_SIZE:
        raise MessageFailure(
            "Message payload exceeds the 2048-byte cookie limit; use FallbackStorage or SessionStorage."
        )
    return signed


class CookieStorage(BaseStorage):
    """Signed-cookie storage.

    Adds accumulate in ``scope[PENDING_KEY]`` during the request (re-reading
    the incoming cookie would overwrite earlier messages); the middleware
    ships the final Set-Cookie header on the response.
    """

    def _cookie_value(self, scope: dict[str, Any]) -> str | None:
        from http.cookies import SimpleCookie

        jar = SimpleCookie()
        for key, value in scope.get("headers", []):
            if key.decode().lower() == "cookie":
                jar.load(value.decode())
        morsel = jar.get(COOKIE_NAME)
        return morsel.value if morsel else None

    def _load(self, scope: dict[str, Any]) -> list[Message]:
        if PENDING_KEY in scope:  # in-request buffer wins over the cookie
            raw = scope[PENDING_KEY]
        else:
            raw_cookie = self._cookie_value(scope)
            if not raw_cookie:
                return []
            try:
                unsigned = TimestampSigner(salt="ronnie.messages").unsign(raw_cookie)
                padding = "=" * (-len(unsigned) % 4)
                raw = json.loads(base64.urlsafe_b64decode(unsigned + padding))
            except Exception:
                return []
        return [m for m in (Message.from_list(r) for r in raw) if m is not None]

    def _persist(self, scope: dict[str, Any], messages: list[Message]) -> None:
        encode_cookie_payload(messages)  # size validation (may raise)
        scope[PENDING_KEY] = [m.as_list() for m in messages]

    def _clear(self, scope: dict[str, Any]) -> None:
        scope[PENDING_KEY] = []  # middleware expires the cookie


class MessageFailure(Exception):
    pass


class FallbackStorage(BaseStorage):
    """Cookie first; overflow falls back to the session."""

    def __init__(self) -> None:
        self._cookie = CookieStorage()
        self._session = SessionStorage()

    def _load(self, scope: dict[str, Any]) -> list[Message]:
        return self._cookie._load(scope) + self._session._load(scope)

    def _persist(self, scope: dict[str, Any], messages: list[Message]) -> None:
        try:
            self._cookie._persist(scope, messages)
            self._session._clear(scope)
        except MessageFailure:
            scope.pop(PENDING_KEY, None)
            self._session._persist(scope, messages)

    def _clear(self, scope: dict[str, Any]) -> None:
        self._cookie._clear(scope)
        self._session._clear(scope)
