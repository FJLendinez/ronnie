"""contrib.sessions: pluggable session engines (cookie / db / cache / custom)."""

from __future__ import annotations

from typing import Any

__all__ = ["SESSION_KEY_SCOPE", "cycle_key", "flush"]


def _session_scope(request_or_session: Any) -> dict[str, Any]:
    scope = getattr(request_or_session, "scope", None)
    if isinstance(scope, dict):
        return scope
    raise TypeError("flush()/cycle_key() expect a request object.")


def flush(request: Any) -> None:
    """Delete the session entirely (data + cookie). Use on logout."""
    scope = _session_scope(request)
    session = scope.get("session")
    if isinstance(session, dict):
        session.clear()
    scope["ronnie.session_flush"] = True


def cycle_key(request: Any) -> None:
    """Get a fresh session key keeping the data (anti session-fixation).

    With the db engine the old row is deleted and a new key is issued on the
    next response. With signed-cookie sessions the payload is client-side, so
    there is no key to cycle (rotation happens naturally on re-signing).
    """
    scope = _session_scope(request)
    session = scope.get("session")
    if session is None:
        return
    from .engines import DbSessionEngine

    engine = DbSessionEngine()
    old_key = _cookie_value(scope)
    if old_key:
        data = dict(session)
        engine.delete(old_key)
        fresh = type(session)(data)
        fresh.modified = True
        scope["session"] = fresh


def _cookie_value(scope: dict[str, Any]) -> str | None:
    from http.cookies import SimpleCookie

    from ...conf import settings as ronnie_settings

    jar = SimpleCookie()
    for key, value in scope.get("headers", []):
        if key.decode().lower() == "cookie":
            jar.load(value.decode())
    morsel = jar.get(ronnie_settings.SESSION_COOKIE_NAME)
    return morsel.value if morsel else None
