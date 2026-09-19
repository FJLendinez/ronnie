"""Settings access for Ronnie — equivalent of ``django.conf``.

Access settings as object attributes::

    from ronnie.conf import settings
    if settings.DEBUG: ...

The active settings module is resolved from, in order:

1. ``settings._setup(module)`` called explicitly (``ronnie.setup()`` does this),
2. the ``RONNIE_SETTINGS_MODULE`` environment variable,
3. ``settings.configure(**options)`` for standalone usage (scripts, tests).

Resolution order for a value: project settings module → ``global_settings``
defaults. Callable settings (Django >= 5.1 behaviour) are evaluated on first
access and the result is cached.
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from . import global_settings
from .core.exceptions import ImproperlyConfigured

__all__ = ["SETTINGS_MODULE_ENV", "LazySettings", "UserSettingsHolder", "settings"]

SETTINGS_MODULE_ENV = "RONNIE_SETTINGS_MODULE"


class Settings:
    """Materialized settings: global defaults overridden by a project module."""

    def __init__(self, settings_module: str) -> None:
        # Load defaults first, then let the project module override them.
        for setting in dir(global_settings):
            if setting.isupper():
                setattr(self, setting, getattr(global_settings, setting))

        self.SETTINGS_MODULE = settings_module

        mod = importlib.import_module(self.SETTINGS_MODULE)
        for setting in dir(mod):
            if setting.isupper():
                setattr(self, setting, getattr(mod, setting))


class UserSettingsHolder:
    """Holder for runtime overrides layered over a defaults object.

    Base of ``override_settings`` (Fase 5): attribute reads fall back to the
    wrapped defaults, writes shadow them.
    """

    def __init__(self, default_settings: Any) -> None:
        self.__dict__["_default_settings"] = default_settings

    def __getattr__(self, name: str) -> Any:
        if not name.isupper():
            raise AttributeError(f"setting {name!r} is not defined")
        return getattr(self._default_settings, name)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)


class LazySettings:
    """Lazy proxy around a ``Settings`` (or ``UserSettingsHolder``) instance.

    Nothing is imported or evaluated until the first attribute access.
    """

    _wrapped: Settings | UserSettingsHolder | None

    def __init__(self) -> None:
        self._wrapped = None

    # -- setup ---------------------------------------------------------------

    def _setup(self, module: str | None = None) -> None:
        """Load the settings module (explicit ``module`` wins over env var)."""
        if self.configured:
            raise RuntimeError("Settings already configured.")
        module = module or os.environ.get(SETTINGS_MODULE_ENV)
        if not module:
            raise ImproperlyConfigured(
                "Requested settings, but settings are not configured. "
                f"You must either define the environment variable {SETTINGS_MODULE_ENV} "
                "or call settings.configure() before accessing settings."
            )
        self._wrapped = Settings(module)

    def configure(self, default_settings: Any = None, **options: Any) -> None:
        """Configure settings programmatically (standalone/tests usage)."""
        if self.configured:
            raise RuntimeError("Settings already configured.")
        holder = UserSettingsHolder(default_settings or global_settings)
        for name, value in options.items():
            if not name.isupper():
                raise TypeError(f"Setting names must be UPPERCASE; got {name!r}")
            setattr(holder, name, value)
        self._wrapped = holder

    # -- proxy protocol ------------------------------------------------------

    @property
    def configured(self) -> bool:
        """Return True if the settings have already been configured."""
        return self._wrapped is not None

    @property
    def SETTINGS_MODULE(self) -> str:
        if self._wrapped is None:
            self._setup()
            assert self._wrapped is not None
        return getattr(self._wrapped, "SETTINGS_MODULE", "")

    def __getattr__(self, name: str) -> Any:
        if self._wrapped is None:
            self._setup()
            assert self._wrapped is not None  # _setup configures or raises
        if name.startswith("_"):
            raise AttributeError(name)
        val = getattr(self._wrapped, name)
        if callable(val):
            val = val()
            setattr(self._wrapped, name, val)  # cache the resolved value
        self.__dict__[name] = val  # memoize on the proxy too
        return val

    def __setattr__(self, name: str, value: Any) -> None:
        """Set a value on the wrapped settings.

        Django parity: mutation is technically possible but unsupported
        (tests swap ``_wrapped`` instead via ``override_settings``). Clear the
        memoized value so the new one is visible.
        """
        if name == "_wrapped":
            self.__dict__.clear()
            self.__dict__["_wrapped"] = value
            return
        if self._wrapped is None:
            self._setup()
            assert self._wrapped is not None
        self.__dict__.pop(name, None)
        setattr(self._wrapped, name, value)

    def __delattr__(self, name: str) -> None:
        if name == "_wrapped":
            raise TypeError("can't delete _wrapped.")
        if self._wrapped is None:
            self._setup()
            assert self._wrapped is not None
        self.__dict__.pop(name, None)
        delattr(self._wrapped, name)

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        if self._wrapped is None:
            return "<LazySettings [Unevaluated]>"
        return f"<LazySettings {getattr(self._wrapped, 'SETTINGS_MODULE', '(configured)')}>"


settings = LazySettings()
