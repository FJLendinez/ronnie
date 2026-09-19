"""contrib.messages: flash messages (django.contrib.messages equivalent).

Usage::

    from ronnie.contrib.messages import messages, Alerts

    @rt
    def save(req):
        messages.success(req, "Saved!")
        return Redirect(show)

    def show(req):
        return Titled("Show", Alerts(req))  # renders and clears flashes
"""

from __future__ import annotations

from typing import Any

from .storage import Message

__all__ = [
    "DEBUG",
    "ERROR",
    "INFO",
    "SUCCESS",
    "WARNING",
    "Alerts",
    "Message",
    "add_message",
    "get_messages",
    "messages",
]

DEBUG, INFO, SUCCESS, WARNING, ERROR = 10, 20, 25, 30, 40


def _storage() -> Any:
    import importlib

    from ...conf import settings

    path = getattr(settings._wrapped, "MESSAGE_STORAGE", None) or (
        "ronnie.contrib.messages.storage.FallbackStorage"
    )
    module_path, _, attr = path.rpartition(".")
    cls = getattr(importlib.import_module(module_path), attr)
    return cls()


def _fail_silently_default() -> bool:
    from ...apps import apps

    return not apps.is_installed("ronnie.contrib.messages")


def add_message(
    request: Any, level: int, message: str, extra_tags: str = "", fail_silently: bool = False
) -> None:
    try:
        _storage().add(request, level, message, extra_tags)
    except Exception:
        if not fail_silently:
            raise


def get_messages(request: Any, *, consume: bool = True) -> list[Message]:
    """Read pending messages (clearing them by default, Django-style)."""
    messages: list[Message] = _storage().read(request, consume=consume)
    return messages


def Alerts(request: Any, extra: str = "") -> Any:
    """Render pending flash messages as alert divs (Pico-friendly)."""
    from fasthtml.common import Div

    items = get_messages(request, consume=True)
    if not items:
        return ""
    return Div(
        *[Div(m.message, role="alert", cls=f"alert {m.tags} {extra}".strip()) for m in items],
        cls="ronnie-messages",
    )


class _MessagesAPI:
    """Shortcut namespace: ``messages.success(request, "...")`` et al."""

    def _add(self, request: Any, level: int, message: str, extra_tags: str) -> None:
        add_message(request, level, message, extra_tags, fail_silently=True)

    def debug(self, request: Any, message: str, extra_tags: str = "") -> None:
        self._add(request, DEBUG, message, extra_tags)

    def info(self, request: Any, message: str, extra_tags: str = "") -> None:
        self._add(request, INFO, message, extra_tags)

    def success(self, request: Any, message: str, extra_tags: str = "") -> None:
        self._add(request, SUCCESS, message, extra_tags)

    def warning(self, request: Any, message: str, extra_tags: str = "") -> None:
        self._add(request, WARNING, message, extra_tags)

    def error(self, request: Any, message: str, extra_tags: str = "") -> None:
        self._add(request, ERROR, message, extra_tags)


messages = _MessagesAPI()
