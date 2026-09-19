"""unittest integration — ``SimpleTestCase`` and ``RonnieTestCase``.

``RonnieTestCase`` gives every test a throwaway sqlite database with all app
tables installed (the closest practical equivalent of Django's per-test
transaction rollback without an ORM).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from .assertions import AssertionsMixin
from .client import RonnieTestClient
from .utils import override_settings

__all__ = ["RonnieTestCase", "SimpleTestCase"]


class SimpleTestCase(AssertionsMixin, unittest.TestCase):
    """Test case with a fresh RonnieTestClient per test; no database setup."""

    client_class: type[RonnieTestClient] = RonnieTestClient
    settings_overrides: override_settings | None = None  # class-level overrides
    _class_override: override_settings | None = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        decorator = getattr(cls, "_ronnie_override_settings", None) or cls.settings_overrides
        if decorator is not None:
            decorator.enable()
            cls._class_override = decorator

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._class_override is not None:
            cls._class_override.disable()
            cls._class_override = None
        super().tearDownClass()

    def setUp(self) -> None:
        super().setUp()
        self.client = self.client_class()

    def settings(self, **kwargs: Any) -> override_settings:
        """``with self.settings(DEBUG=True):`` — per-block override."""
        return override_settings(**kwargs)


class RonnieTestCase(SimpleTestCase):
    """Test case with a throwaway sqlite database per test."""

    installed_apps: list[str] | None = None  # defaults to settings.INSTALLED_APPS
    _apps_override: override_settings | None = None

    def setUp(self) -> None:
        super().setUp()
        from ..db import install_tables, reset_databases_cache

        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_override = override_settings(
            DATABASES={
                "default": {
                    "ENGINE": "sqlite",
                    "NAME": Path(self._tmpdir.name) / "test.sqlite3",
                }
            }
        )
        self._db_override.enable()
        reset_databases_cache()
        if self.installed_apps is not None:
            self._apps_override = override_settings(INSTALLED_APPS=self.installed_apps)
            self._apps_override.enable()
            from ..apps import apps

            apps.clear_data()
            import ronnie

            ronnie.setup()
        install_tables()

    def tearDown(self) -> None:
        from ..db import reset_databases_cache

        reset_databases_cache()
        if self._apps_override is not None:
            self._apps_override.disable()
            self._apps_override = None
        self._db_override.disable()
        self._tmpdir.cleanup()
        super().tearDown()
