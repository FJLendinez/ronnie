"""User model and helpers (MiniDataAPI edition of django.contrib.auth.models)."""

import dataclasses
import datetime as dt
import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any


@dataclass
class User:
    """A user row. Password stores a Django-format hash (never plaintext)."""

    id: int | None = None
    username: str = ""
    email: str = ""
    password: str = ""
    first_name: str = ""
    last_name: str = ""
    is_active: bool = True
    is_staff: bool = False
    is_superuser: bool = False
    date_joined: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    # Simplified permissions (Django parity via M2M tables is a non-goal):
    # comma-separated "<app_label>.<codename>" strings.
    user_permissions: str = ""

    is_authenticated = True  # Django parity for templates/handlers

    def get_session_auth_hash(self) -> str:
        """HMAC of the password hash — invalidate sessions on password change."""
        from ...conf import settings

        key = hashlib.sha256((settings.SECRET_KEY or "").encode()).digest()
        return hmac.new(key, self.password.encode(), hashlib.sha256).hexdigest()

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def has_perm(self, perm: str) -> bool:
        if self.is_superuser:
            return True
        perms = {p.strip() for p in (self.user_permissions or "").split(",") if p.strip()}
        app_label, _, codename = perm.partition(".")
        return perm in perms or f"{app_label}.*" in perms or (self.is_staff and codename.startswith("view"))

    def __ft__(self) -> Any:  # pragma: no cover - FT integration nicety
        from fasthtml.common import Li

        return Li(self.username)


class AnonymousUser:
    """The not-logged-in user (falsy, no permissions)."""

    id = None
    username = ""
    is_active = False
    is_staff = False
    is_superuser = False
    is_authenticated: bool = False
    user_permissions: str = ""

    def get_session_auth_hash(self) -> str:  # pragma: no cover - never stored
        return ""

    def has_perm(self, perm: str) -> bool:
        return False


TABLES: list[type] = [User]


def get_user_model() -> type:
    """Return the active user class (``AUTH_USER_MODEL`` dotted path)."""
    import importlib

    from ...conf import settings

    path = getattr(settings._wrapped, "AUTH_USER_MODEL", None) or ("ronnie.contrib.auth.User")
    module_path, _, attr = path.rpartition(".")
    cls = getattr(importlib.import_module(module_path), attr)
    assert isinstance(cls, type)
    return cls


def _user_table() -> Any:
    from ...db import get_table

    return get_table(get_user_model())


def get_user_by_username(username: str) -> Any | None:
    table = _user_table()
    for user in table():
        if user.username == username:
            return user
    return None


def create_user(username: str, password: str | None = None, email: str = "", **extra: Any) -> Any:
    """Create a user with a hashed password (raises ValueError on duplicates)."""
    if get_user_by_username(username) is not None:
        raise ValueError(f"Username {username!r} is already taken.")
    from ...core.passwords import make_password

    values: dict[str, Any] = {}
    for f in dataclasses.fields(get_user_model()):
        if f.name == "id":
            continue  # auto primary key
        if f.default is not dataclasses.MISSING:
            values[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            factory: Any = f.default_factory
            values[f.name] = factory()
    values.update(
        username=username,
        email=email,
        password=make_password(password),
        **extra,
    )
    return _user_table().insert(**values)


def create_superuser(username: str, password: str, email: str = "", **extra: Any) -> Any:
    extra.setdefault("is_staff", True)
    extra.setdefault("is_superuser", True)
    return create_user(username, password, email=email, **extra)
