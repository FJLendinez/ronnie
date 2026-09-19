"""Shared fixtures. Settings, app registry and DB connections reset per test."""

from __future__ import annotations

import pytest

from ronnie import conf
from ronnie.apps import apps
from ronnie.db import reset_databases_cache


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """Reset per-test global state: settings, registry, DBs and checks."""
    from ronnie.core import checks as checks_module

    checks_snapshot = {k: list(v) for k, v in checks_module._registry.items()}
    monkeypatch.delenv(conf.SETTINGS_MODULE_ENV, raising=False)
    conf.settings._wrapped = None
    apps.clear_data()
    reset_databases_cache()
    yield
    checks_module._registry.clear()
    checks_module._registry.update(checks_snapshot)
    conf.settings._wrapped = None
    apps.clear_data()
    reset_databases_cache()
