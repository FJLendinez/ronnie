"""Tests for contrib.admin (Fase 11)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ronnie.conf import settings
from ronnie.core.passwords.hashers import PBKDF2PasswordHasher
from ronnie.db import reset_databases_cache

BASE_APPS = [
    "apps.shop",
    "apps.pages",
    "ronnie.contrib.sessions",
    "ronnie.contrib.auth",
    "ronnie.contrib.messages",
    "ronnie.contrib.admin",
]
STACK = [
    "ronnie.middleware.security.SecurityMiddleware",
    "ronnie.middleware.host.HostValidationMiddleware",
    "ronnie.contrib.sessions.middleware.SessionMiddleware",
    "ronnie.middleware.csrf.CsrfMiddleware",
    "ronnie.contrib.auth.middleware.AuthMiddleware",
    "ronnie.contrib.messages.middleware.MessagesMiddleware",
    "ronnie.middleware.clickjacking.XFrameOptionsMiddleware",
]


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(PBKDF2PasswordHasher, "iterations", 1_000)


@pytest.fixture()
def admin_env(tmp_path: Path):
    import ronnie

    settings.configure(
        SECRET_KEY="admin-key",
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        INSTALLED_APPS=BASE_APPS,
        MIDDLEWARE=STACK,
        DATABASES={"default": {"ENGINE": "sqlite", "NAME": tmp_path / "admin.sqlite3"}},
        LOGIN_REDIRECT_URL="/admin/",
        LOGOUT_REDIRECT_URL="/pages/",
    )
    ronnie.setup()
    from ronnie.db import install_tables

    install_tables()
    from apps.shop.models import Product
    from ronnie.contrib.auth.models import create_user
    from ronnie.db import get_table

    create_user("staffer", "staff-pass-1", is_staff=True)
    create_user("peasant", "peasant-pass-1")
    table = get_table(Product)
    table.insert(name="mug", price=5.0)
    table.insert(name="plate", price=9.0)
    table.insert(name="fork", price=1.5)
    yield
    reset_databases_cache()


def make_client() -> TestClient:
    from ronnie.core.asgi import get_asgi_application

    return TestClient(get_asgi_application())


def login(client: TestClient, username: str, password: str) -> None:
    page = client.get("/accounts/login").text
    tag = re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page)
    token = re.search(r'value="([^"]+)"', tag.group(0)).group(1)
    response = client.post(
        "/accounts/login",
        data={"username": username, "password": password, "csrfmiddlewaretoken": token},
        follow_redirects=True,
    )
    assert response.status_code == 200


def _token(client: TestClient, path: str) -> str:
    page = client.get(path).text
    tag = re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page)
    return re.search(r'value="([^"]+)"', tag.group(0)).group(1)


class TestAccess:
    def test_anonymous_redirected_to_login(self, admin_env):
        client = make_client()
        response = client.get("/admin/shop/product", follow_redirects=False)
        assert response.status_code == 303
        assert "/accounts/login" in response.headers["location"]

    def test_non_staff_rejected(self, admin_env):
        client = make_client()
        login(client, "peasant", "peasant-pass-1")
        response = client.get("/admin/shop/product", follow_redirects=False)
        assert response.status_code == 303

    def test_staff_sees_changelist(self, admin_env):
        client = make_client()
        login(client, "staffer", "staff-pass-1")
        response = client.get("/admin/shop/product")
        assert response.status_code == 200
        assert "mug" in response.text
        assert "plate" in response.text

    def test_index_lists_registered_model(self, admin_env):
        client = make_client()
        login(client, "staffer", "staff-pass-1")
        response = client.get("/admin/")
        assert "Product" in response.text


class TestChangeList:
    def _staff(self):
        client = make_client()
        login(client, "staffer", "staff-pass-1")
        return client

    def test_ordering_from_model_admin(self, admin_env):
        client = self._staff()
        body = client.get("/admin/shop/product").text
        pos_plate = body.find("plate")  # highest price first
        pos_fork = body.find("fork")
        assert 0 < pos_plate < pos_fork

    def test_search_filters_rows(self, admin_env):
        client = self._staff()
        body = client.get("/admin/shop/product?q=mug").text
        assert "mug" in body
        assert "plate" not in body

    def test_list_filter(self, admin_env):
        client = self._staff()
        body = client.get("/admin/shop/product?f=name&v=fork").text
        assert "fork" in body
        assert "mug" not in body

    def test_pagination(self, admin_env):
        client = self._staff()
        page1 = client.get("/admin/shop/product").text  # per_page=2
        assert page1.count("<tr") <= 3  # header + 2 rows
        page2 = client.get("/admin/shop/product?page=2").text
        assert "fork" in page2

    def test_unknown_model_rejected(self, admin_env):
        client = self._staff()
        response = client.get("/admin/shop/nope")
        assert response.status_code == 200
        assert "Unknown model" in response.text


class TestCrud:
    def _staff(self):
        client = make_client()
        login(client, "staffer", "staff-pass-1")
        return client

    def test_add_object(self, admin_env):
        client = self._staff()
        token = _token(client, "/admin/shop/product/add")
        response = client.post(
            "/admin/shop/product/add",
            data={"name": "spoon", "price": "2.25", "csrfmiddlewaretoken": token},
            follow_redirects=True,
        )
        assert "spoon" in response.text  # appears in the changelist
        assert "added" in response.text.lower() or "Product" in response.text

    def test_change_object(self, admin_env):
        client = self._staff()
        from apps.shop.models import Product
        from ronnie.db import get_table

        row = get_table(Product)()[0]
        pk = row.id
        token = _token(client, f"/admin/shop/product/{pk}/change")
        response = client.post(
            f"/admin/shop/product/{pk}/change",
            data={"name": "mug-xl", "price": "7.5", "csrfmiddlewaretoken": token},
            follow_redirects=True,
        )
        assert "mug-xl" in response.text
        updated = get_table(Product)[int(pk)]
        assert updated.name == "mug-xl"

    def test_delete_object(self, admin_env):
        client = self._staff()
        from apps.shop.models import Product
        from ronnie.db import get_table

        table = get_table(Product)
        pk = table()[0].id
        before = len(table())
        client.get(f"/admin/shop/product/{pk}/delete", follow_redirects=True)
        assert len(table()) == before - 1

    def test_delete_selected_action(self, admin_env):
        client = self._staff()
        from apps.shop.models import Product
        from ronnie.db import get_table

        table = get_table(Product)
        pks = [str(r.id) for r in table()]
        token = _token(client, "/admin/shop/product")
        data = {"action": "delete_selected", "csrfmiddlewaretoken": token}
        data.update({f"sel-{pk}": pk for pk in pks})
        client.post("/admin/shop/product/action", data=data, follow_redirects=True)
        assert len(table()) == 0


class TestRegistry:
    def test_duplicate_registration_rejected(self, admin_env):
        from apps.shop.models import Product
        from ronnie.contrib.admin import site

        with pytest.raises(ValueError, match="already registered"):
            site.register(Product)

    def test_unregister(self, admin_env):
        from apps.shop.models import Product
        from ronnie.contrib.admin import site

        admin = site.get_model_admin(Product)
        assert admin.search_fields == ("name",)
        site.unregister(Product)
        site.register(Product)  # back to defaults for other tests
