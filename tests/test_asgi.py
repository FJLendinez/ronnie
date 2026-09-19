"""Tests for the ASGI factory, routing and static files (Fase 4)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from ronnie.conf import settings
from ronnie.core.asgi import get_asgi_application, resolve_middleware
from ronnie.core.exceptions import ImproperlyConfigured


def make_client(**overrides) -> TestClient:
    defaults: dict = {
        "SECRET_KEY": "test-key",
        "DEBUG": False,
        "INSTALLED_APPS": ["apps.pages"],
        "MIDDLEWARE": [],
    }
    defaults.update(overrides)
    settings.configure(**defaults)
    app = get_asgi_application()
    return TestClient(app)


class TestAppFactory:
    def test_app_index_route_served(self):
        with make_client() as client:
            response = client.get("/pages/")
            assert response.status_code == 200
            assert "pages index" in response.text

    def test_subroute_served(self):
        with make_client() as client:
            response = client.get("/pages/about")
            assert response.status_code == 200
            assert "about page" in response.text

    def test_custom_404_page(self):
        with make_client() as client:
            response = client.get("/does-not-exist")
            assert response.status_code == 404
            assert "not found" in response.text.lower()

    def test_app_without_routes_is_fine(self):
        with make_client(INSTALLED_APPS=["apps.news", "apps.pages"]) as client:
            assert client.get("/pages/").status_code == 200

    def test_duplicate_routes_rejected(self):
        settings.configure(SECRET_KEY="k", INSTALLED_APPS=["apps.pages", "apps.copy"], MIDDLEWARE=[])
        with pytest.raises(ImproperlyConfigured, match="Duplicate route"):
            get_asgi_application()

    def test_middleware_from_settings(self):
        with make_client(MIDDLEWARE=["sample_middleware.XHeaderMiddleware"]) as client:
            response = client.get("/pages/")
            assert response.headers["x-ronnie"] == "on"


class TestMiddlewareResolution:
    def test_bad_path_raises(self):
        with pytest.raises(ImproperlyConfigured, match="dotted paths"):
            resolve_middleware(["NotDotted"])

    def test_unknown_middleware_raises(self):
        with pytest.raises(ImproperlyConfigured, match="Cannot import"):
            resolve_middleware(["no.such.Middleware"])

    def test_resolves_to_starlette_middleware(self):
        result = resolve_middleware(["sample_middleware.XHeaderMiddleware"])
        assert result[0].cls is __import__("sample_middleware").XHeaderMiddleware


class TestStaticFiles:
    def test_static_mounted_when_dir_exists(self, tmp_path):
        (tmp_path / "app.css").write_text("body{}")
        with make_client(STATIC_ROOT=str(tmp_path)) as client:
            response = client.get("/static/app.css")
            assert response.status_code == 200
            assert "body" in response.text

    def test_static_not_mounted_when_missing(self, tmp_path):
        with make_client(STATIC_ROOT=str(tmp_path / "nope")) as client:
            assert client.get("/static/app.css").status_code == 404
