"""Settings overrides for tests — equivalent of ``django.test.utils``.

Use as context manager, method decorator, or class attribute on
``RonnieTestCase`` subclasses::

    with override_settings(DEBUG=True):
        ...

    @override_settings(DEBUG=True)
    def test_debug(self): ...

    class MyTests(RonnieTestCase):
        override_settings = override_settings(TIME_ZONE="UTC")
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from ..conf import UserSettingsHolder, settings
from ..core.signals import setting_changed

__all__ = ["modify_settings", "override_settings"]


class override_settings:
    """Temporarily override settings, sending ``setting_changed`` signals."""

    def __init__(self, **kwargs: Any) -> None:
        self.options: dict[str, Any] = kwargs
        self.wrapped: Any = None

    def enable(self) -> None:
        if not settings.configured:
            settings._setup()  # standard ImproperlyConfigured if nothing to load
        self.wrapped = settings._wrapped
        override = UserSettingsHolder(self.wrapped)
        for name, value in self.options.items():
            setattr(override, name, value)
        settings._wrapped = override
        for name, value in self.options.items():
            setting_changed.send(sender=self, setting=name, value=value, enter=True)

    def disable(self) -> None:
        if self.wrapped is None:
            return
        settings._wrapped = self.wrapped
        self.wrapped = None
        for name in self.options:
            setting_changed.send(sender=self, setting=name, enter=False)

    # -- context manager ------------------------------------------------------------

    def __enter__(self) -> override_settings:
        self.enable()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disable()

    # -- decorator --------------------------------------------------------------------

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        if isinstance(func, type):
            # Decorator on a TestCase class: store for setUpClass to apply.
            setattr(func, "_ronnie_override_settings", self)  # noqa: B010
            return func

        def inner(*args: Any, **kw: Any) -> Any:
            with self:
                return func(*args, **kw)

        inner.__name__ = getattr(func, "__name__", "wrapped")
        inner.__doc__ = func.__doc__
        return inner


class modify_settings(override_settings):
    """Override list-style settings with append/prepend/remove operations::

    with modify_settings(MIDDLEWARE={"append": "x.M"}):
        ...
    """

    def __init__(self, *args: Any, **kwargs: dict[str, list[str]]) -> None:
        self.operations = args[0] if args else kwargs
        super().__init__()

    def enable(self) -> None:
        if not settings.configured:
            settings._setup()  # standard ImproperlyConfigured if nothing to load
        self.wrapped = settings._wrapped
        override = UserSettingsHolder(self.wrapped)
        for name, operations in self.operations.items():
            current = list(getattr(settings, name, []))
            for action, values in operations.items():
                values = list(values)
                if action == "append":
                    current += values
                elif action == "prepend":
                    current = values + current
                elif action == "remove":
                    current = [v for v in current if v not in values]
                else:
                    raise ValueError(f"Unknown modify_settings action {action!r}.")
                setattr(override, name, current)
            setting_changed.send(sender=self, setting=name, value=current, enter=True)
        settings._wrapped = override

    def disable(self) -> None:
        if self.wrapped is None:
            return
        settings._wrapped = self.wrapped
        self.wrapped = None
        for name in self.operations:
            setting_changed.send(sender=self, setting=name, enter=False)


@contextmanager
def capture_signaled_settings() -> Iterator[list[tuple[str, Any]]]:
    """Test helper: capture (setting, value) pairs sent via setting_changed."""
    events: list[tuple[str, Any]] = []

    def receiver(sender: Any, **kw: Any) -> None:
        if kw.get("enter"):
            events.append((kw.get("setting", ""), kw.get("value")))

    setting_changed.connect(receiver, weak=False)
    try:
        yield events
    finally:
        setting_changed.disconnect(receiver)
