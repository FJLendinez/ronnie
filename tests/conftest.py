"""Shared fixtures. Settings, app registry and DB connections reset per test."""

from __future__ import annotations

import pytest

from ronnie import conf
from ronnie.apps import apps
from ronnie.db import reset_databases_cache


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """Reset the lazy settings singleton and app registry around every test."""
    monkeypatch.delenv(conf.SETTINGS_MODULE_ENV, raising=False)
    conf.settings._wrapped = None
    apps.clear_data()
    reset_databases_cache()
    yield
    conf.settings._wrapped = None
    apps.clear_data()
    reset_databases_cache()
