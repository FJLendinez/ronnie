"""Tests for the testing framework itself (Fase 5, dogfooding)."""

from __future__ import annotations

import pytest

from ronnie.conf import settings
from ronnie.core.management import call_command
from ronnie.db import get_table
from ronnie.testing import RonnieTestCase, RonnieTestClient, SimpleTestCase, override_settings
from ronnie.testing.utils import capture_signaled_settings


def configure_app():
    settings.configure(
        SECRET_KEY="k",
        INSTALLED_APPS=["apps.pages", "apps.shop"],
        MIDDLEWARE=[],
    )


class TestOverrideSettings:
    def test_context_manager_overrides_and_restores(self):
        settings.configure(DEBUG=False)
        assert settings.DEBUG is False
        with override_settings(DEBUG=True):
            assert settings.DEBUG is True
        assert settings.DEBUG is False

    def test_function_decorator(self):
        settings.configure(TIME_ZONE="UTC")

        @override_settings(TIME_ZONE="Europe/Madrid")
        def probe():
            return settings.TIME_ZONE

        assert probe() == "Europe/Madrid"
        assert settings.TIME_ZONE == "UTC"

    def test_nested_overrides(self):
        settings.configure(DEBUG=False)
        with override_settings(DEBUG=True):
            with override_settings(DEBUG=False):
                assert settings.DEBUG is False
            assert settings.DEBUG is True
        assert settings.DEBUG is False

    def test_setting_changed_signal(self):
        settings.configure(DEBUG=False)
        with capture_signaled_settings() as events, override_settings(DEBUG=True):
            pass
        assert events == [("DEBUG", True)]


class TestSelfSettingsHelper:
    def test_with_settings_block(self):
        settings.configure(DEBUG=False)

        class Case(SimpleTestCase):
            def runTest(self):
                pass

        case = Case("runTest")
        case.setUp()
        try:
            with case.settings(DEBUG=True):
                assert settings.DEBUG is True
            assert settings.DEBUG is False
        finally:
            case.tearDown()

    def test_class_override_settings_applied(self):
        settings.configure(TIME_ZONE="UTC")

        class Case(SimpleTestCase):
            settings_overrides = override_settings(TIME_ZONE="Atlantic/Canary")

            def runTest(self):
                pass

        Case.setUpClass()
        try:
            assert settings.TIME_ZONE == "Atlantic/Canary"
        finally:
            Case.tearDownClass()


class TestRonnieTestClient:
    def test_get_renders_app_route(self):
        configure_app()
        assert "pages index" in RonnieTestClient().get("/pages/").text

    def test_htmx_helper_sends_header(self):
        configure_app()
        client = RonnieTestClient()
        assert "is-htmx" in client.htmx("get", "/pages/echo_htmx").text
        assert "not-htmx" in client.get("/pages/echo_htmx").text

    def test_follow_redirects(self):
        configure_app()
        client = RonnieTestClient(follow_redirects=True)
        response = client.get("/pages/go")
        assert response.status_code == 200
        assert "pages index" in response.text
        assert response.history

    def test_redirect_not_followed_by_default(self):
        configure_app()
        response = RonnieTestClient().get("/pages/go")
        assert response.status_code in (301, 302, 303, 307)

    def test_lazy_client_allows_late_settings(self, monkeypatch):
        client = RonnieTestClient()  # built before settings exist
        monkeypatch.setenv("RONNIE_SETTINGS_MODULE", "app_settings")
        assert client.get("/pages/").status_code == 200


class DbCase(RonnieTestCase):
    """Inserts in one test must not be visible in another."""

    __test__ = False  # helper for TestRonnieTestCase, not a collected test

    def runTest(self):
        pass

    def _insert_one(self):
        from apps.shop.models import Product

        return get_table(Product).insert(name="thing", price=1.5)


class TestRonnieTestCase:
    def _run(self, method: str):
        case = DbCase(method)
        case.setUp()
        try:
            getattr(case, method)()
        finally:
            case.tearDown()

    def test_db_isolated_between_tests(self):
        configure_app()

        def insert_and_check():
            case = DbCase("_insert_one")
            case.setUp()
            try:
                case._insert_one()
                from apps.shop.models import Product

                assert len(get_table(Product)()) == 1
            finally:
                case.tearDown()

        insert_and_check()

        # A second, fresh case must see an empty table (no leak).
        case2 = DbCase("runTest")
        case2.setUp()
        try:
            from apps.shop.models import Product

            assert len(get_table(Product)()) == 0
        finally:
            case2.tearDown()

    def test_assertions_with_client(self):
        configure_app()
        case = DbCase("runTest")
        case.setUp()
        try:
            response = case.client.get("/pages/")
            case.assertContains(response, "pages index")
            case.assertRedirects(case.client.get("/pages/go", follow_redirects=True), "/pages/")
        finally:
            case.tearDown()


@pytest.fixture
def app_env(monkeypatch):
    monkeypatch.setenv("RONNIE_SETTINGS_MODULE", "app_settings")


class TestPytestFixtures:
    def test_client_fixture(self, app_env, client):
        assert client.get("/pages/").status_code == 200

    def test_db_fixture_installs_tables(self, app_env, db):
        from apps.shop.models import Product

        table = get_table(Product)
        table.insert(name="café", price=2.0)
        assert len(table()) == 1


class TestTestCommand:
    def test_runs_pytest(self, monkeypatch):
        import pytest as pytest_mod

        captured: dict = {}
        monkeypatch.setattr(pytest_mod, "main", lambda args: captured.update(args=args) or 0)
        call_command("test", "tests/test_conf.py")
        assert "tests/test_conf.py" in captured["args"]

    def test_failfast_flag(self, monkeypatch):
        import pytest as pytest_mod

        captured: dict = {}
        monkeypatch.setattr(pytest_mod, "main", lambda args: captured.update(args=args) or 0)
        call_command("test", failfast=True)
        assert "-x" in captured["args"]

    def test_failure_raises_command_error(self, monkeypatch):
        import pytest as pytest_mod

        monkeypatch.setattr(pytest_mod, "main", lambda args: 1)
        with pytest.raises(Exception, match="Tests failed"):
            call_command("test")
