"""Access-control decorators (Django-compatible behaviour, FastHTML-friendly).

The wrapped handler must declare a ``req``/``request`` (or ``auth``) parameter
so the decorator can inspect the logged-in user. FastHTML always calls
handlers with keyword arguments, so signatures stay intact.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

__all__ = ["login_required", "permission_required", "user_passes_test"]


def _user_of(kwargs: dict[str, Any]) -> Any:
    request = kwargs.get("req") or kwargs.get("request")
    user = None
    if request is not None:
        user = getattr(request, "user", None) or request.scope.get("user")
    if user is None:
        user = kwargs.get("auth")
    if user is None and request is not None:
        user = request.scope.get("auth")
    return user


def _redirect_to_login(kwargs: dict[str, Any], login_url: str, redirect_field_name: str) -> Any:
    from fasthtml.common import Redirect

    request = kwargs.get("req") or kwargs.get("request")
    next_path = request.url.path if request is not None else "/"
    separator = "&" if "?" in login_url else "?"
    return Redirect(f"{login_url}{separator}{redirect_field_name}={quote(next_path)}")


def user_passes_test(
    test_func: Callable[[Any], bool], login_url: str | None = None, redirect_field_name: str = "next"
) -> Callable[[Any], Any]:
    """Decorator: redirect to login unless ``test_func(user)`` is true."""

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from ...conf import settings

            user = _user_of(kwargs)
            if not getattr(user, "is_authenticated", False) or not test_func(user):
                url = login_url or settings.LOGIN_URL
                return _redirect_to_login(kwargs, url, redirect_field_name)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def login_required(
    view: Callable[..., Any] | None = None, *, login_url: str | None = None, redirect_field_name: str = "next"
) -> Any:
    """Decorator: require a logged-in user, else redirect to ``LOGIN_URL``."""
    decorator = user_passes_test(
        lambda user: True, login_url=login_url, redirect_field_name=redirect_field_name
    )
    return decorator(view) if view is not None else decorator


def permission_required(
    perm: str, login_url: str | None = None, raise_exception: bool = False
) -> Callable[[Any], Any]:
    """Decorator: require ``user.has_perm(perm)``."""

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from ...conf import settings
            from ...core.exceptions import PermissionDenied

            user = _user_of(kwargs)
            if not getattr(user, "is_authenticated", False):
                url = login_url or settings.LOGIN_URL
                return _redirect_to_login(kwargs, url, "next")
            if not user.has_perm(perm):
                if raise_exception:
                    raise PermissionDenied(f"Missing permission {perm!r}.")
                return _redirect_to_login(kwargs, login_url or settings.LOGIN_URL, "next")
            return view(*args, **kwargs)

        return wrapper

    return decorator
