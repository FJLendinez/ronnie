"""Tests for ronnie.conf (Fase 1)."""

from __future__ import annotations

import pytest

from ronnie import conf
from ronnie.core.exceptions import ImproperlyConfigured


class TestSettingsResolution:
    def test_defaults_applied_for_missing_settings(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        assert conf.settings.configured is False
        assert conf.settings.TIME_ZONE == "UTC"  # from global_settings
        assert conf.settings.USE_TZ is True

    def test_project_module_overrides_defaults(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        assert conf.settings.DEBUG is True
        assert conf.settings.SECRET_KEY == "test-secret-key"
        assert conf.settings.CUSTOM_VALUE == "custom"

    def test_lowercase_module_attrs_ignored(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        with pytest.raises(AttributeError):
            _ = conf.settings._CALLS

    def test_settings_module_recorded(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        assert conf.settings.SETTINGS_MODULE == "sample_settings"

    def test_explicit_module_beats_env(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "does_not_exist_1")
        conf.settings._setup("sample_settings")
        assert conf.settings.SECRET_KEY == "test-secret-key"

    def test_missing_module_raises_improperly_configured(self):
        with pytest.raises(ImproperlyConfigured, match="RONNIE_SETTINGS_MODULE"):
            _ = conf.settings.DEBUG

    def test_unknown_setting_raises_attributeerror(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        with pytest.raises(AttributeError):
            _ = conf.settings.NOPE


class TestConfigure:
    def test_configure_standalone(self):
        conf.settings.configure(DEBUG=True, CUSTOM_VALUE=42)
        assert conf.settings.DEBUG is True
        assert conf.settings.CUSTOM_VALUE == 42
        assert conf.settings.TIME_ZONE == "UTC"  # defaults still visible
        assert conf.settings.configured is True

    def test_configure_rejects_lowercase(self):
        with pytest.raises(TypeError, match="UPPERCASE"):
            conf.settings.configure(not_upper=1)

    def test_configure_twice_raises(self):
        conf.settings.configure(DEBUG=True)
        with pytest.raises(RuntimeError, match="already configured"):
            conf.settings.configure(DEBUG=False)

    def test_setup_after_configure_raises(self):
        conf.settings.configure(DEBUG=True)
        with pytest.raises(RuntimeError, match="already configured"):
            conf.settings._setup("sample_settings")

    def test_configure_with_custom_defaults(self):
        class MyDefaults:
            DEBUG = True
            TIME_ZONE = "Europe/Madrid"

        conf.settings.configure(MyDefaults, DEBUG=False)
        assert conf.settings.DEBUG is False
        assert conf.settings.TIME_ZONE == "Europe/Madrid"
        # custom defaults replace global_settings entirely: unknown names raise
        with pytest.raises(AttributeError):
            _ = conf.settings.USE_TZ

    def test_unknown_on_holder_raises(self):
        conf.settings.configure()
        with pytest.raises(AttributeError):
            _ = conf.settings.UNKNOWN_THING


class TestCallableSettings:
    @pytest.fixture(autouse=True)
    def _reset_sample_counter(self, monkeypatch):
        monkeypatch.setattr("sample_settings._CALLS", {"n": 0})

    def test_callables_resolved_on_access(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        assert conf.settings.COMPUTED_SETTING == 42

    def test_callable_result_cached(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        assert conf.settings.COMPUTED_SETTING == 42
        assert conf.settings.COMPUTED_SETTING == 42
        assert conf.settings.CALL_COUNT == 1  # evaluated exactly once


class TestProxySemantics:
    def test_setattr_visible_and_updates_memo(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        _ = conf.settings.COMPUTED_SETTING  # memoize resolved value
        conf.settings.DEBUG = False
        assert conf.settings.DEBUG is False

    def test_swapping_wrapped_clears_memos(self, monkeypatch):
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        assert conf.settings.SECRET_KEY == "test-secret-key"
        holder = conf.UserSettingsHolder(conf.global_settings)
        holder.SECRET_KEY = "other"
        conf.settings._wrapped = holder
        assert conf.settings.SECRET_KEY == "other"
        assert conf.settings.DEBUG is False  # global default, not the module's

    def test_bool_is_true(self):
        assert bool(conf.settings) is True

    def test_repr(self, monkeypatch):
        assert "Unevaluated" in repr(conf.settings)
        monkeypatch.setenv(conf.SETTINGS_MODULE_ENV, "sample_settings")
        _ = conf.settings.DEBUG
        assert "sample_settings" in repr(conf.settings)
