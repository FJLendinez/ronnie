"""Tests for the app registry (Fase 2)."""

from __future__ import annotations

import sys

import pytest

from apps import blog as blog_app
from ronnie.apps import AppConfig
from ronnie.apps import apps as registry
from ronnie.core.exceptions import AppRegistryNotReady, ImproperlyConfigured


@pytest.fixture(autouse=True)
def _reset_registry_and_events():
    registry.clear_data()
    sys.modules.pop("apps.blog.models", None)  # force re-import per test
    blog_app.EVENTS.clear()
    yield
    registry.clear_data()
    sys.modules.pop("apps.blog.models", None)
    blog_app.EVENTS.clear()


class TestPopulate:
    def test_three_phases_in_order(self):
        registry.populate(["apps.blog"])
        assert registry.ready is True
        assert blog_app.EVENTS == ["models-imported", "ready"]  # models before ready()

    def test_populate_is_idempotent(self):
        registry.populate(["apps.blog"])
        registry.populate(["apps.blog"])  # second call is a no-op
        assert blog_app.EVENTS == ["models-imported", "ready"]

    def test_populate_reentrant_raises(self, monkeypatch):
        monkeypatch.setattr(AppConfig, "ready", lambda self: registry.populate(["apps.news"]))
        with pytest.raises(RuntimeError, match="reentrant"):
            registry.populate(["apps.news"])

    def test_configs_keep_installed_order(self):
        registry.populate(["apps.blog", "apps.news"])
        assert [c.label for c in registry.get_app_configs()] == ["blog", "news"]

    def test_autodetects_single_appconfig(self):
        registry.populate(["apps.blog"])
        cfg = registry.get_app_config("blog")
        assert type(cfg).__name__ == "BlogConfig"
        assert cfg.verbose_name == "The Blog"

    def test_plain_package_gets_base_config(self):
        registry.populate(["apps.news"])
        cfg = registry.get_app_config("news")
        assert type(cfg) is AppConfig
        assert cfg.verbose_name == "News"
        assert cfg.models_module is None

    def test_default_true_disambiguates_multiple_configs(self):
        registry.populate(["apps.polls"])
        cfg = registry.get_app_config("poll")
        assert type(cfg).__name__ == "PollsConfig"

    def test_explicit_config_path_entry(self):
        registry.populate(["apps.blog.apps.BlogConfig"])
        assert registry.get_app_config("blog").verbose_name == "The Blog"

    def test_duplicate_label_raises(self):
        with pytest.raises(ImproperlyConfigured, match="duplicate label 'blog'"):
            registry.populate(["apps.blog", "apps.other"])

    def test_invalid_label_raises(self):
        with pytest.raises(ImproperlyConfigured, match="valid Python identifier"):
            registry.populate(["apps.badlabel"])

    def test_mismatched_name_raises(self):
        with pytest.raises(ImproperlyConfigured, match="doesn't match"):
            registry.populate(["apps.mismatch"])

    def test_broken_entry_raises(self):
        with pytest.raises(ImproperlyConfigured, match="Cannot import"):
            registry.populate(["apps.news.apps.NonexistentPath"])


class TestQueries:
    def test_not_ready_raises(self):
        with pytest.raises(AppRegistryNotReady):
            list(registry.get_app_configs())

    def test_get_app_config_unknown_label(self):
        registry.populate(["apps.news"])
        with pytest.raises(LookupError, match="news2"):
            registry.get_app_config("news2")

    def test_is_installed(self):
        registry.populate(["apps.news"])
        assert registry.is_installed("apps.news") is True
        assert registry.is_installed("apps.blog") is False

    def test_repr(self):
        registry.populate(["apps.news"])
        assert "news" in repr(registry.get_app_config("news"))
