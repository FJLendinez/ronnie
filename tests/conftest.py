"""Shared fixtures. Settings and the app registry are reset around every test."""

from __future__ import annotations

import pytest

from ronnie import conf
from ronnie.apps import apps


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """Reset the lazy settings singleton before/after each test."""
    monkeypatch.delenv(conf.SETTINGS_MODULE_ENV, raising=False)
    conf.settings._wrapped = None
    apps.clear_data()
    yield
    conf.settings._wrapped = None
    apps.clear_data()
