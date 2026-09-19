"""Pluggable session engines.

``SESSION_ENGINE`` selects one:

- ``"cookie"`` (default): signed-cookie sessions (Starlette), zero setup.
- ``"db"``: server-side rows in the ``ronnie_session`` table (needs the
  ``ronnie.contrib.sessions`` app installed and migrated).
- ``"cache"``: cache-framework backed (added with the cache framework).

A custom engine is any dotted path to a module (or object) providing the
``SessionEngine`` protocol below.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import secrets
from typing import Any, Protocol, runtime_checkable

from ...core.exceptions import ImproperlyConfigured

__all__ = ["DbSessionEngine", "SessionEngine", "new_session_key", "resolve_engine"]

COOKIE_ENGINE = "cookie"
_DB_ENGINE = "db"
_CACHE_ENGINE = "cache"


def new_session_key() -> str:
    return secrets.token_hex(16)


@runtime_checkable
class SessionEngine(Protocol):
    """Server-side storage contract for sessions."""

    def load(self, session_key: str) -> dict[str, Any] | None: ...

    def save(self, session_key: str, data: dict[str, Any], max_age: int) -> None: ...

    def delete(self, session_key: str) -> None: ...

    def new_key(self) -> str: ...

    def clear_expired(self) -> int: ...


def resolve_engine(name: str) -> str | SessionEngine:
    """Return "cookie" (middleware handles it) or a SessionEngine instance."""
    if name == COOKIE_ENGINE:
        return COOKIE_ENGINE
    if name == _DB_ENGINE:
        return DbSessionEngine()
    if name == _CACHE_ENGINE:
        raise ImproperlyConfigured(
            "SESSION_ENGINE='cache' requires the cache framework (ronnie.cache); "
            "configure CACHES first (see the cache framework docs)."
        )
    if "." in name:  # dotted path to a module/object exposing the protocol
        import importlib

        module_path, _, attr = name.rpartition(".")
        try:
            candidate = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError):
            try:  # module-style path: engine module with DbSessionEngine-like class
                candidate = importlib.import_module(name)
            except ImportError as err:
                raise ImproperlyConfigured(f"Cannot import session engine {name!r}") from err
            candidate = getattr(candidate, "Engine", None) or getattr(candidate, "engine", None)
            if candidate is None:
                raise ImproperlyConfigured(f"Session engine {name!r} exposes no Engine.") from None
        engine = candidate() if isinstance(candidate, type) else candidate
        if not isinstance(engine, SessionEngine):
            raise ImproperlyConfigured(f"{name!r} does not implement the SessionEngine protocol.")
        return engine
    raise ImproperlyConfigured(
        f"Unknown SESSION_ENGINE {name!r} (use 'cookie', 'db', 'cache' or a dotted path)."
    )


def _utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class DbSessionEngine:
    """Store sessions as rows via the MiniDataAPI (table ``ronnie_session``)."""

    def __init__(self) -> None:
        self._table: Any = None

    def new_key(self) -> str:
        return new_session_key()

    @property
    def table(self) -> Any:
        if self._table is None:
            from ...db import get_table
            from .models import RonnieSession

            self._table = get_table(RonnieSession, pk="session_key")
        return self._table

    def load(self, session_key: str) -> dict[str, Any] | None:
        try:
            row = self.table[session_key]
        except Exception:
            return None
        expire = row.expire_date
        if expire:
            try:
                expired = dt.datetime.fromisoformat(expire) < dt.datetime.now(dt.timezone.utc)
            except ValueError:
                expired = False
            if expired:
                self.delete(session_key)
                return None
        try:
            data = json.loads(row.data or "{}")
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def save(self, session_key: str, data: dict[str, Any], max_age: int) -> None:
        expire = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=max_age)).isoformat()
        payload = json.dumps(data)
        try:
            row = self.table[session_key]  # fastlite updates via row objects
            row.data = payload
            row.expire_date = expire
            self.table.update(row)
        except Exception:
            self.table.insert(session_key=session_key, data=payload, expire_date=expire)

    def delete(self, session_key: str) -> None:
        with contextlib.suppress(Exception):  # row already gone
            self.table.delete(session_key)

    def clear_expired(self) -> int:
        now = dt.datetime.now(dt.timezone.utc)
        removed = 0
        for row in list(self.table()):
            if row.expire_date:
                try:
                    if dt.datetime.fromisoformat(row.expire_date) < now:
                        self.delete(row.session_key)
                        removed += 1
                except ValueError:
                    continue
        return removed
