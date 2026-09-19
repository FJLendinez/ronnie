"""Authentication backends (AUTHENTICATION_BACKENDS setting)."""

from __future__ import annotations

from typing import Any

from ...core.exceptions import PermissionDenied

__all__ = ["ModelBackend", "get_backends"]

DEFAULT_BACKENDS = ["ronnie.contrib.auth.backends.ModelBackend"]


class ModelBackend:
    """Username + password against the user table (Django's ModelBackend)."""

    def authenticate(
        self,
        request: Any = None,
        username: str | None = None,
        password: str | None = None,
        **credentials: Any,
    ) -> Any | None:
        from ...core.passwords import check_password
        from .models import get_user_by_username

        if username is None or password is None:
            return None
        user = get_user_by_username(str(username))
        if user is None:
            # Constant-ish work even for unknown users (timing).
            from ...core.passwords import make_password

            make_password(password)
            return None
        if not user.is_active:
            return None
        if check_password(password, user.password):
            return user
        return None

    def get_user(self, user_id: Any) -> Any | None:
        from .models import _user_table

        try:
            return _user_table()[int(user_id)]
        except (TypeError, ValueError, Exception):
            return None


def get_backends() -> list[Any]:
    import importlib

    from ...conf import settings

    paths = list(getattr(settings._wrapped, "AUTHENTICATION_BACKENDS", None) or DEFAULT_BACKENDS)
    backends = []
    for path in paths:
        module_path, _, attr = path.rpartition(".")
        try:
            cls = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError) as exc:
            from ...core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured(f"Cannot import auth backend {path!r}: {exc}") from exc
        backends.append(cls() if isinstance(cls, type) else cls)
    return backends


def authenticate(request: Any = None, **credentials: Any) -> Any | None:
    """Try every backend; a backend raising PermissionDenied stops the chain."""
    for backend in get_backends():
        try:
            user = backend.authenticate(request, **credentials)
        except PermissionDenied:
            return None
        if user is not None:
            user.backend = f"{type(backend).__module__}.{type(backend).__name__}"
            return user
    return None
