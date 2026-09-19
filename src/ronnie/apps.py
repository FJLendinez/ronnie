"""Application registry — equivalent of ``django.apps``.

``INSTALLED_APPS`` entries may be either a package path (``"apps.blog"``) or
an explicit ``AppConfig`` path (``"apps.blog.apps.BlogConfig"``). When the
package has an ``apps.py`` module with exactly one ``AppConfig`` subclass, it
is used automatically (several subclasses: the one with ``default = True``).

Population happens in three phases, in ``INSTALLED_APPS`` order:

1. import each entry and instantiate its ``AppConfig``,
2. import each ``<app>.models`` submodule (registers MiniDataAPI tables),
3. call every ``AppConfig.ready()`` hook.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Iterator
from inspect import getmembers, isclass
from pathlib import Path
from types import ModuleType

from .core.exceptions import AppRegistryNotReady, ImproperlyConfigured

__all__ = ["AppConfig", "Apps", "apps"]


class AppConfig:
    """Configuration and lifecycle for an installed application.

    Subclass (conventionally in ``<app>/apps.py``) and override attributes::

        class BlogConfig(AppConfig):
            name = "apps.blog"          # required when declared in apps.py
            label = "blog"              # default: last component of name
            verbose_name = "Blog"

            def ready(self):            # called once, after all models load
                ...                     # connect signals, register tasks...
    """

    # Class-level overridables (annotation-only: instances always assign them)
    name: str
    label: str
    verbose_name: str
    default = False

    def __init__(self, app_name: str, app_module: ModuleType | None) -> None:
        self.name = app_name
        self.module = app_module
        # Explicit class attribute wins over the derived default.
        self.label = getattr(type(self), "label", None) or app_name.rpartition(".")[2]
        self.verbose_name = getattr(type(self), "verbose_name", None) or self.label.title()
        self.path = self._app_path(app_module)
        self.models_module: ModuleType | None = None

    # -- construction helpers -------------------------------------------------

    def _app_path(self, app_module: ModuleType | None) -> Path | None:
        file = getattr(app_module, "__file__", None) if app_module else None
        return Path(file).resolve().parent if file else None

    @classmethod
    def create(cls, entry: str) -> AppConfig:
        """Build an AppConfig from an INSTALLED_APPS entry (module or class path)."""
        app_name: str
        config_class: type[AppConfig] | None = None

        try:
            app_module = importlib.import_module(entry)
            app_name = entry
        except ImportError:
            # Maybe the entry is "pkg.apps.Config" — resolve the class.
            mod_path, _, cls_name = entry.rpartition(".")
            try:
                mod = importlib.import_module(mod_path)
                config_class = getattr(mod, cls_name)
            except (ImportError, AttributeError) as exc:
                raise ImproperlyConfigured(f"Cannot import '{entry}': {exc}") from exc
            if not (isclass(config_class) and issubclass(config_class, AppConfig)):
                raise ImproperlyConfigured(f"'{entry}' is not an AppConfig class.") from None
            declared = getattr(config_class, "name", None)
            if not declared:
                raise ImproperlyConfigured(
                    f"{config_class.__name__} must define a 'name' attribute."
                ) from None
            app_name = declared
            app_module = importlib.import_module(app_name)
        else:
            # Look for an apps.py with an AppConfig subclass.
            config_class = cls._autodetect(app_name)

        if config_class is not None:
            declared = getattr(config_class, "name", None)
            if declared and declared != app_name:
                raise ImproperlyConfigured(
                    f"{config_class.__name__}.name ({declared!r}) doesn't match its module ({app_name!r})."
                )
            return config_class(app_name, app_module)

        return cls(app_name, app_module)

    @classmethod
    def _autodetect(cls, app_name: str) -> type[AppConfig] | None:
        apps_module_path = f"{app_name}.apps"
        try:
            apps_module = importlib.import_module(apps_module_path)
        except ImportError as exc:
            name = getattr(exc, "name", None)
            if name in (apps_module_path, app_name):
                return None  # no apps.py — plain package
            raise  # apps.py exists but is broken
        candidates = [
            obj
            for _, obj in getmembers(apps_module, isclass)
            if issubclass(obj, AppConfig) and obj is not AppConfig and obj.__module__ == apps_module_path
        ]
        if not candidates:
            return None
        if len(candidates) > 1:
            defaults = [c for c in candidates if c.default]
            if len(defaults) != 1:
                names = ", ".join(c.__name__ for c in candidates)
                raise ImproperlyConfigured(
                    f"{apps_module_path} defines several AppConfigs ({names}); "
                    "exactly one must set default = True."
                )
            return defaults[0]
        return candidates[0]

    # -- lifecycle ------------------------------------------------------------

    def ready(self) -> None:
        """Hook called once after all apps' models are imported.

        Must be idempotent, must not touch the database, and should import
        models/tasks lazily (inside the method, not at module level).
        """

    def import_modules(self) -> None:
        """Phase 2: import this app's models and tasks submodules if present."""
        self.models_module = self._import_optional("models")
        self._import_optional("tasks")

    def _import_optional(self, suffix: str) -> ModuleType | None:
        module_path = f"{self.name}.{suffix}"
        try:
            return importlib.import_module(module_path)
        except ImportError as exc:
            if getattr(exc, "name", None) == module_path:
                return None  # module doesn't exist — fine
            raise  # module exists but is broken

    def __repr__(self) -> str:
        return f"<{type(self).__name__} '{self.label}'>"


class Apps:
    """The application registry (singleton: ``ronnie.apps.apps``)."""

    def __init__(self) -> None:
        self.app_configs: dict[str, AppConfig] = {}
        self.apps_ready = False
        self.models_ready = False
        self.ready = False

    # -- population -----------------------------------------------------------

    def populate(self, installed_apps: Iterable[str] | None = None) -> None:
        """Load application configurations and initialize the registry."""
        if self.ready:
            return  # idempotent: ronnie.setup() may be called repeatedly
        if self.apps_ready:
            msg = "populate() isn't reentrant."
            raise RuntimeError(msg)

        # Phase 1: create configs.
        for entry in installed_apps or []:
            config = AppConfig.create(entry)
            if not config.label.isidentifier():
                raise ImproperlyConfigured(f"App label {config.label!r} is not a valid Python identifier.")
            if config.label in self.app_configs:
                raise ImproperlyConfigured(
                    f"Application labels aren't unique: duplicate label {config.label!r} ({entry})."
                )
            self.app_configs[config.label] = config
        self.apps_ready = True

        # Phase 2: import models and tasks modules.
        for config in self.app_configs.values():
            config.import_modules()
        self.models_ready = True

        # Phase 3: run ready() hooks.
        for config in self.app_configs.values():
            config.ready()
        self.ready = True

    # -- queries ---------------------------------------------------------------

    def get_app_configs(self) -> Iterator[AppConfig]:
        """Yield app configs in INSTALLED_APPS order."""
        self.check_apps_ready()
        yield from self.app_configs.values()

    def get_app_config(self, app_label: str) -> AppConfig:
        self.check_apps_ready()
        try:
            return self.app_configs[app_label]
        except KeyError:
            raise LookupError(f"No installed app with label '{app_label}'.") from None

    def is_installed(self, app_name: str) -> bool:
        self.check_apps_ready()
        return any(cfg.name == app_name for cfg in self.app_configs.values())

    def check_apps_ready(self) -> None:
        if not self.apps_ready:
            raise AppRegistryNotReady("Apps aren't loaded yet.")

    # -- test support -----------------------------------------------------------

    def clear_data(self) -> None:
        """Reset the registry to its pristine state (test helper)."""
        self.app_configs = {}
        self.apps_ready = self.models_ready = self.ready = False


apps = Apps()
