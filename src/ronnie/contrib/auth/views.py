"""Built-in auth views: login, logout, password change (FT + Pico, HTMX-ready)."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Article, Button, Div, Form, Input, Strong, Titled

from ...core.routing import Router
from ..sessions import flush
from .api import login as do_login
from .api import update_session_auth_hash
from .backends import authenticate
from .middleware import (
    AuthMiddleware,  # noqa: F401 - re-exported for MIDDLEWARE
    get_user_from_scope,
)

__all__ = ["rt"]

rt = Router("accounts")


def _login_form(req: Any, error: str = "", next_url: str = "") -> Any:
    from ...middleware.csrf import CsrfToken

    error_block = Div(Strong(error), style="color:#b3261e") if error else ""
    return Titled(
        "Sign in",
        Article(
            Form(
                CsrfToken(req),
                Input(type="hidden", name="next", value=next_url),
                error_block,
                Input(name="username", placeholder="Username", required=True),
                Input(type="password", name="password", placeholder="Password", required=True),
                Button("Sign in", type="submit"),
                action="/accounts/login",
                method="post",
            )
        ),
    )


@rt("/login")
def get(req, next: str = ""):
    return _login_form(req, next_url=next)


@rt("/login")
def post(req, username: str = "", password: str = "", next: str = ""):
    from ...conf import settings

    user = authenticate(req, username=username, password=password)
    if user is None:
        return _login_form(req, error="Invalid username or password.", next_url=next)
    do_login(req, user)
    from fasthtml.common import Redirect

    target = next or settings.LOGIN_REDIRECT_URL
    return Redirect(target)


@rt("/logout")
def post(req):
    from fasthtml.common import Redirect

    from ...conf import settings

    flush(req)
    return Redirect(settings.LOGOUT_REDIRECT_URL)


@rt("/password_change")
def get(req):
    from ...middleware.csrf import CsrfToken

    user = get_user_from_scope(req.scope)
    if not getattr(user, "is_authenticated", False):
        from fasthtml.common import Redirect

        return Redirect("/accounts/login?next=/accounts/password_change")
    return Titled(
        "Change password",
        Article(
            Form(
                CsrfToken(req),
                Input(type="password", name="old_password", placeholder="Current password"),
                Input(type="password", name="new_password1", placeholder="New password"),
                Input(type="password", name="new_password2", placeholder="Repeat new password"),
                Button("Change password", type="submit"),
                action="/accounts/password_change",
                method="post",
            )
        ),
    )


@rt("/password_change")
def post(req, old_password: str = "", new_password1: str = "", new_password2: str = ""):
    from fasthtml.common import Redirect

    from ...conf import settings
    from ...core.exceptions import ValidationError
    from ...core.passwords import check_password, make_password, validate_password
    from .models import _user_table

    user = get_user_from_scope(req.scope)
    if not getattr(user, "is_authenticated", False):
        return Redirect("/accounts/login")

    target = "/accounts/password_change"
    if not check_password(old_password, user.password):
        return Redirect(f"{target}?error=current")
    if new_password1 != new_password2:
        return Redirect(f"{target}?error=mismatch")
    try:
        validate_password(new_password1, user=user)
    except ValidationError:
        return Redirect(f"{target}?error=invalid")

    user.password = make_password(new_password1)
    _user_table().update(user)
    update_session_auth_hash(req, user)  # keep this session alive
    return Redirect(settings.LOGIN_REDIRECT_URL)
