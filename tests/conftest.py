"""Shared fixtures. The settings singleton is reset around every test."""

from __future__ import annotations

import pytest

from ronnie import conf


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """Reset the lazy settings singleton before/after each test."""
    monkeypatch.delenv(conf.SETTINGS_MODULE_ENV, raising=False)
    conf.settings._wrapped = None
    yield
    conf.settings._wrapped = None
