"""Auth API: login/logout/get_user (django.contrib.auth equivalents)."""

from __future__ import annotations

import hmac
from typing import Any

__all__ = ["get_user", "login", "logout", "update_session_auth_hash"]

SESSION_KEY = "_auth_user_id"
HASH_KEY = "_auth_user_hash"


def _scope(request_or_scope: Any) -> dict[str, Any]:
    scope = (
        request_or_scope if isinstance(request_or_scope, dict) else getattr(request_or_scope, "scope", None)
    )
    if not isinstance(scope, dict):  # pragma: no cover - defensive
        raise TypeError("Expected a request or an ASGI scope.")
    return scope


def login(request: Any, user: Any) -> None:
    """Persist the user in the session (rotating the key: anti-fixation)."""
    scope = _scope(request)
    session = scope.get("session")
    if not isinstance(session, dict):  # pragma: no cover - middleware missing
        from ...core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured("login() requires the session middleware.")

    from ..sessions import cycle_key

    cycle_key(request)  # no-op for signed-cookie sessions
    session = scope.get("session") or session
    session[SESSION_KEY] = str(user.id)
    session[HASH_KEY] = user.get_session_auth_hash()


def logout(request: Any) -> None:
    """Flush the session entirely (never fails, like Django's logout)."""
    import contextlib

    from ..sessions import flush

    with contextlib.suppress(Exception):  # logout must not raise
        flush(request)


def get_user(request_or_scope: Any) -> Any:
    """Return the logged-in user or AnonymousUser, verifying the session hash."""
    from .models import AnonymousUser, _user_table

    scope = _scope(request_or_scope)
    session = scope.get("session") or {}
    user_id = session.get(SESSION_KEY)
    if not user_id:
        return AnonymousUser()
    try:
        user = _user_table()[int(user_id)]
    except Exception:
        return AnonymousUser()
    if not getattr(user, "is_active", False):
        return AnonymousUser()
    stored_hash = session.get(HASH_KEY)
    if stored_hash is not None and not hmac.compare_digest(stored_hash, user.get_session_auth_hash()):
        return AnonymousUser()  # password changed elsewhere: re-login
    return user


def update_session_auth_hash(request: Any, user: Any) -> None:
    """Keep the current session valid after a password change."""
    scope = _scope(request)
    session = scope.get("session")
    if isinstance(session, dict):
        session[HASH_KEY] = user.get_session_auth_hash()
