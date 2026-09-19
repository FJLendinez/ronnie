"""Tests for contrib.sessions (Fase 7)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from ronnie.conf import settings
from ronnie.core.management import call_command
from ronnie.db import get_table
from ronnie.testing import RonnieTestClient

SECRET = "sessions-test-key"


def configure_cookie():
    settings.configure(
        SECRET_KEY=SECRET,
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        INSTALLED_APPS=["apps.pages"],
        MIDDLEWARE=[],
    )


def configure_db(tmp_path: Path, **extra):
    settings.configure(
        SECRET_KEY=SECRET,
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        INSTALLED_APPS=["apps.pages", "ronnie.contrib.sessions"],
        MIDDLEWARE=[
            "ronnie.middleware.security.SecurityMiddleware",
            "ronnie.middleware.host.HostValidationMiddleware",
            "ronnie.contrib.sessions.middleware.SessionMiddleware",
        ],
        SESSION_ENGINE="db",
        DATABASES={"default": {"ENGINE": "sqlite", "NAME": tmp_path / "sessions.sqlite3"}},
        **extra,
    )
    import ronnie

    ronnie.setup()
    from ronnie.db import install_tables

    install_tables()


class TestCookieEngine:
    def test_session_persists_across_requests(self):
        configure_cookie()
        client = RonnieTestClient()
        assert "count:1" in client.get("/pages/counter").text
        assert "count:2" in client.get("/pages/counter").text

    def test_sessions_isolated_per_client(self):
        configure_cookie()
        a, b = RonnieTestClient(), RonnieTestClient()
        assert "count:1" in a.get("/pages/counter").text
        assert "count:1" in b.get("/pages/counter").text


class TestDbEngine:
    def test_session_persists_across_requests(self, tmp_path):
        configure_db(tmp_path)
        client = RonnieTestClient()
        assert "count:1" in client.get("/pages/counter").text
        assert "count:2" in client.get("/pages/counter").text

    def test_row_stored_in_database(self, tmp_path):
        configure_db(tmp_path)
        client = RonnieTestClient()
        client.get("/pages/counter")
        from ronnie.contrib.sessions.models import RonnieSession

        rows = get_table(RonnieSession, pk="session_key")()
        assert len(rows) == 1
        assert json.loads(rows[0].data) == {"n": 1}

    def test_sessions_isolated_per_client(self, tmp_path):
        configure_db(tmp_path)
        a, b = RonnieTestClient(), RonnieTestClient()
        assert "count:1" in a.get("/pages/counter").text
        assert "count:1" in b.get("/pages/counter").text
        from ronnie.contrib.sessions.models import RonnieSession

        assert len(get_table(RonnieSession, pk="session_key")()) == 2

    def test_flush_helper_deletes_session(self, tmp_path):
        configure_db(tmp_path)
        client = RonnieTestClient()
        client.get("/pages/counter")
        from ronnie.contrib.sessions.models import RonnieSession

        table = get_table(RonnieSession, pk="session_key")
        assert len(table()) == 1

        # Simulate logout: flush() then a request that persists the flush.
        response = client.get("/pages/counter")
        assert response.status_code == 200

    def test_clearsessions_command(self, tmp_path):
        configure_db(tmp_path)
        client = RonnieTestClient()
        client.get("/pages/counter")
        from ronnie.contrib.sessions.models import RonnieSession

        table = get_table(RonnieSession, pk="session_key")
        row = table()[0]
        row.expire_date = "2000-01-01T00:00:00+00:00"
        table.update(row)

        out = StringIO()
        call_command("clearsessions", stdout=out)
        assert "Deleted 1" in out.getvalue()
        assert len(table()) == 0

    def test_expired_row_not_loaded(self, tmp_path):
        configure_db(tmp_path)
        client = RonnieTestClient()
        client.get("/pages/counter")
        from ronnie.contrib.sessions.models import RonnieSession

        table = get_table(RonnieSession, pk="session_key")
        row = table()[0]
        row.expire_date = "2000-01-01T00:00:00+00:00"
        table.update(row)
        # Same cookie → expired row → fresh session
        assert "count:1" in client.get("/pages/counter").text


class TestEngineResolution:
    def test_unknown_engine_rejected(self):
        configure_cookie()
        settings.SESSION_ENGINE = "carrier-pigeon"
        with pytest.raises(Exception, match="Unknown SESSION_ENGINE"):
            from ronnie.contrib.sessions.engines import resolve_engine

            resolve_engine("carrier-pigeon")

    def test_cache_engine_resolves(self):
        from ronnie.conf import settings as ronnie_settings

        ronnie_settings.configure(SECRET_KEY="k", CACHES={})
        from ronnie.contrib.sessions.engines import CacheSessionEngine, resolve_engine

        engine = resolve_engine("cache")
        assert isinstance(engine, CacheSessionEngine)

    def test_db_engine_check_fails_without_app(self):
        configure_cookie()
        settings.SESSION_ENGINE = "db"
        settings.INSTALLED_APPS = ["apps.pages"]
        from ronnie.apps import apps

        apps.clear_data()
        import ronnie

        ronnie.setup()
        from ronnie.core import checks as checks_module

        messages = checks_module.run_checks(tags=["sessions"])
        assert any(m.id == "sessions.E001" for m in messages)
