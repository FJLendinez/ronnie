"""Tests for contrib.humanize and contrib.redirects (Fase 12)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ronnie.conf import settings
from ronnie.contrib.humanize import (
    apnumber,
    intcomma,
    intword,
    naturalday,
    naturaltime,
    ordinal,
)
from ronnie.db import reset_databases_cache


@pytest.fixture(autouse=True)
def _es_default():
    settings.configure(SECRET_KEY="k", HUMANIZE_LANGUAGE="es")
    yield


class TestHumanize:
    def test_apnumber(self):
        assert apnumber(1) == "uno"
        assert apnumber(9) == "nueve"
        assert apnumber(10) == "10"
        assert apnumber(3, language="en") == "three"

    def test_intcomma(self):
        assert intcomma(4_500_000) == "4.500.000"
        assert intcomma(4_500_000, language="en") == "4,500,000"
        assert intcomma(1234.5) == "1.234,50"
        assert intcomma(300) == "300"

    def test_intword(self):
        assert intword(1_200_000_000) == "1,2 mil millones"
        assert intword(1_200_000_000, language="en") == "1.2 billion"
        assert intword(2_000_000) == "2,0 millones"
        assert intword(42) == "42"

    def test_ordinal(self):
        assert ordinal(1) == "1.º"
        assert ordinal(3) == "3.º"
        assert ordinal(1, language="en") == "1st"
        assert ordinal(2, language="en") == "2nd"
        assert ordinal(11, language="en") == "11th"
        assert ordinal(-4, language="en") == "-4"

    def test_naturalday(self):
        today = dt.datetime.now()
        assert naturalday(today) == "hoy"
        assert naturalday(today, language="en") == "today"
        assert naturalday(today + dt.timedelta(days=1)) == "mañana"
        assert naturalday(today - dt.timedelta(days=1)) == "ayer"

    def test_naturaltime_es(self):
        now = dt.datetime(2026, 9, 19, 12, 0, 0)
        assert naturaltime(now - dt.timedelta(seconds=5), now=now) == "ahora mismo"
        assert naturaltime(now - dt.timedelta(minutes=4), now=now) == "hace 4 minutos"
        assert naturaltime(now - dt.timedelta(hours=1), now=now) == "hace 1 hora"
        assert naturaltime(now + dt.timedelta(hours=3), now=now) == "en 3 horas"
        assert naturaltime(now - dt.timedelta(days=2), now=now) == "hace 2 días"

    def test_naturaltime_en(self):
        now = dt.datetime(2026, 9, 19, 12, 0, 0)
        assert naturaltime(now - dt.timedelta(seconds=45), language="en", now=now) == "45 seconds ago"
        assert naturaltime(now + dt.timedelta(minutes=1), language="en", now=now) == "in 1 minute"

    def test_ft_component(self):
        from fasthtml.core import to_xml

        from ronnie.contrib.humanize import HumanTime

        now = dt.datetime.now()
        xml = to_xml(HumanTime(now - dt.timedelta(minutes=2)))
        assert "<time" in xml and "hace 2 minutos" in xml


class TestRedirects:
    @pytest.fixture()
    def redirect_env(self, tmp_path: Path):
        import ronnie
        from ronnie.apps import apps

        # The autouse fixture already configured settings: mutate instead.
        for key, value in {
            "DEBUG": False,
            "ALLOWED_HOSTS": ["testserver"],
            "INSTALLED_APPS": ["apps.pages", "ronnie.contrib.redirects"],
            "MIDDLEWARE": ["ronnie.contrib.redirects.middleware.RedirectFallbackMiddleware"],
            "DATABASES": {"default": {"ENGINE": "sqlite", "NAME": tmp_path / "r.sqlite3"}},
        }.items():
            setattr(settings, key, value)
        apps.clear_data()
        ronnie.setup()
        from ronnie.db import install_tables

        install_tables()
        from ronnie.contrib.redirects.models import RonnieRedirect
        from ronnie.db import get_table

        table = get_table(RonnieRedirect, pk="old_path")
        table.insert(old_path="/old/", new_path="/pages/", response_code=301)
        table.insert(old_path="/gone/", new_path="", response_code=410)
        yield
        reset_databases_cache()

    def _client(self) -> TestClient:
        from ronnie.core.asgi import get_asgi_application

        return TestClient(get_asgi_application())

    def test_permanent_redirect_on_404(self, redirect_env):
        with self._client() as client:
            response = client.get("/old/", follow_redirects=False)
            assert response.status_code == 301
            assert response.headers["location"] == "/pages/"

    def test_410_for_empty_target(self, redirect_env):
        with self._client() as client:
            assert client.get("/gone/").status_code == 410

    def test_unmatched_404_passes_through(self, redirect_env):
        with self._client() as client:
            assert client.get("/nowhere/").status_code == 404

    def test_working_route_unaffected(self, redirect_env):
        with self._client() as client:
            assert client.get("/pages/").status_code == 200
