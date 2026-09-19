"""System checks framework — a compact ``django.core.checks``.

Register a check::

    from ronnie.core.checks import register, Warning, Error

    @register("blog", deploy=True)
    def check_api_keys(deployment_checks: bool = False) -> list[CheckMessage]:
        ...return [Warning("...", hint="...", id="blog.W001")]

Run with ``ronnie check`` (add ``--deploy`` for deployment-only checks).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

__all__ = [
    "CRITICAL",
    "DEBUG",
    "ERROR",
    "INFO",
    "WARNING",
    "CheckMessage",
    "Critical",
    "Debug",
    "Error",
    "Info",
    "Warning",
    "get_error_count",
    "register",
    "run_checks",
]

# Severity levels (same values as Django)
DEBUG, INFO, WARNING, ERROR, CRITICAL = 10, 20, 30, 40, 50


@dataclass
class CheckMessage:
    level: int
    msg: str
    hint: str | None = None
    id: str | None = None

    def __str__(self) -> str:
        level_letter = {DEBUG: "i", INFO: "i", WARNING: "W", ERROR: "E", CRITICAL: "E"}.get(self.level, "?")
        id_part = f" ({self.id})" if self.id else ""
        hint_part = f"\n\tHINT: {self.hint}" if self.hint else ""
        return f"{level_letter}{id_part}: {self.msg}{hint_part}"

    def is_serious(self, compare: int = ERROR) -> bool:
        return self.level >= compare


class Debug(CheckMessage):
    def __init__(self, msg: str, **kwargs: object) -> None:
        super().__init__(DEBUG, msg, **kwargs)  # type: ignore[arg-type]


class Info(CheckMessage):
    def __init__(self, msg: str, **kwargs: object) -> None:
        super().__init__(INFO, msg, **kwargs)  # type: ignore[arg-type]


class Warning(CheckMessage):
    def __init__(self, msg: str, **kwargs: object) -> None:
        super().__init__(WARNING, msg, **kwargs)  # type: ignore[arg-type]


class Error(CheckMessage):
    def __init__(self, msg: str, **kwargs: object) -> None:
        super().__init__(ERROR, msg, **kwargs)  # type: ignore[arg-type]


class Critical(CheckMessage):
    def __init__(self, msg: str, **kwargs: object) -> None:
        super().__init__(CRITICAL, msg, **kwargs)  # type: ignore[arg-type]


# -- registry ---------------------------------------------------------------------

CheckFunc = Callable[..., list[CheckMessage]]
_registry: dict[str, list[tuple[CheckFunc, bool]]] = {}  # tag -> [(func, deploy_only)]


def register(tag: str = "misc", *, deploy: bool = False) -> Callable[[CheckFunc], CheckFunc]:
    """Register a check function under ``tag``; ``deploy=True`` marks it
    deployment-only (only runs with ``ronnie check --deploy``)."""

    def decorator(func: CheckFunc) -> CheckFunc:
        _registry.setdefault(tag, []).append((func, deploy))
        return func

    return decorator


def run_checks(
    tags: list[str] | None = None,
    include_deployment_checks: bool = False,
) -> list[CheckMessage]:
    """Run all registered checks (or those matching ``tags``) and return messages."""
    from .checks import _registry  # allow monkeypatching in tests

    messages: list[CheckMessage] = []
    for tag, entries in _registry.items():
        if tags is not None and tag not in tags:
            continue
        for func, deploy_only in entries:
            if deploy_only and not include_deployment_checks:
                continue
            messages.extend(func(deployment_checks=include_deployment_checks))
    return sorted(messages, key=lambda m: -m.level)


def get_error_count(messages: list[CheckMessage]) -> int:
    return sum(1 for m in messages if m.is_serious())


# -- built-in checks ----------------------------------------------------------------


@register("settings")
def check_secret_key(deployment_checks: bool = False) -> list[CheckMessage]:
    from ronnie.conf import settings

    try:
        secret = settings.SECRET_KEY
    except Exception:
        return []
    if not secret:
        return [
            Error(
                "SECRET_KEY is empty.",
                hint="Generate one with `ronnie generatesecretkey`.",
                id="settings.E001",
            )
            if deployment_checks
            else Warning(
                "SECRET_KEY is empty; sessions/signing will fail when used.",
                hint="Generate one with `ronnie generatesecretkey`.",
                id="settings.W001",
            )
        ]
    return []


@register("settings", deploy=True)
def check_debug_in_production(deployment_checks: bool = False) -> list[CheckMessage]:
    from ronnie.conf import settings

    try:
        debug = settings.DEBUG
    except Exception:
        return []
    if deployment_checks and debug:
        return [
            Error(
                "DEBUG is True in deployment mode.",
                hint="Set DEBUG = False in production settings.",
                id="settings.E002",
            )
        ]
    return []


@register("security", deploy=True)
def check_secure_settings_for_deploy(deployment_checks: bool = False) -> list[CheckMessage]:
    """Warnings surfaced by `ronnie check --deploy` (safe-by-default nudges)."""
    from ronnie.conf import settings

    try:
        locked = not settings.DEBUG
    except Exception:
        return []
    if not locked:
        return []

    messages: list[CheckMessage] = []
    if not settings.SECURE_SSL_REDIRECT:
        messages.append(
            Warning(
                "SECURE_SSL_REDIRECT is False in deployment mode.",
                hint="Redirect HTTP traffic to HTTPS at the app or proxy level.",
                id="security.W001",
            )
        )
    if not settings.SECURE_HSTS_SECONDS:
        messages.append(
            Warning(
                "SECURE_HSTS_SECONDS is 0: no HSTS header.",
                hint="Set e.g. SECURE_HSTS_SECONDS = 31536000 once TLS is stable.",
                id="security.W002",
            )
        )
    if not settings.SESSION_COOKIE_SECURE:
        messages.append(
            Warning(
                "SESSION_COOKIE_SECURE is False.",
                hint="Set SESSION_COOKIE_SECURE = True when serving over HTTPS.",
                id="security.W003",
            )
        )
    return messages


@register("sessions")
def check_db_session_engine(deployment_checks: bool = False) -> list[CheckMessage]:
    from ronnie.apps import apps
    from ronnie.conf import settings

    try:
        engine = settings.SESSION_ENGINE
    except Exception:
        return []
    if engine == "db" and not apps.is_installed("ronnie.contrib.sessions"):
        return [
            Error(
                "SESSION_ENGINE is 'db' but ronnie.contrib.sessions is not installed.",
                hint="Add 'ronnie.contrib.sessions' to INSTALLED_APPS and run migrate.",
                id="sessions.E001",
            )
        ]
    return []
