"""Tests for contrib.auth (Fase 8)."""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ronnie.conf import settings
from ronnie.core.exceptions import CommandError
from ronnie.core.management import call_command
from ronnie.core.passwords.hashers import PBKDF2PasswordHasher
from ronnie.db import reset_databases_cache

AUTH_ITERATIONS = 1_000  # keep tests fast


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    monkeypatch.setattr(PBKDF2PasswordHasher, "iterations", AUTH_ITERATIONS)


@pytest.fixture()
def auth_env(tmp_path: Path):
    import ronnie

    settings.configure(
        SECRET_KEY="auth-test-key",
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        INSTALLED_APPS=["apps.pages", "ronnie.contrib.sessions", "ronnie.contrib.auth"],
        DATABASES={"default": {"ENGINE": "sqlite", "NAME": tmp_path / "auth.sqlite3"}},
    )
    ronnie.setup()
    from ronnie.db import install_tables

    install_tables()
    yield
    reset_databases_cache()


def make_client() -> TestClient:
    from ronnie.core.asgi import get_asgi_application

    return TestClient(get_asgi_application())


def create_test_user(username="fj", password="s3cret-pass!"):
    from ronnie.contrib.auth.models import create_user

    return create_user(username, password)


def _login(client: TestClient, username: str, password: str):
    page = client.get("/accounts/login").text
    tag = re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page)
    token = re.search(r'value="([^"]+)"', tag.group(0)).group(1)
    return client.post(
        "/accounts/login",
        data={"username": username, "password": password, "csrfmiddlewaretoken": token},
        follow_redirects=False,
    )


class TestUserModel:
    def test_create_user_hashes_password(self, auth_env):
        user = create_test_user()
        assert user.password.startswith("pbkdf2_sha256$")
        assert user.is_authenticated is True

    def test_duplicate_username_rejected(self, auth_env):
        create_test_user()
        with pytest.raises(ValueError, match="already taken"):
            create_test_user()

    def test_session_auth_hash_changes_with_password(self, auth_env):
        user = create_test_user()
        before = user.get_session_auth_hash()
        from ronnie.contrib.auth.models import _user_table
        from ronnie.core.passwords import make_password

        user.password = make_password("other-pass-123")
        _user_table().update(user)
        assert user.get_session_auth_hash() != before

    def test_has_perm(self, auth_env):
        from ronnie.contrib.auth.models import create_user

        superu = create_user("rooty", "rooty-pass-1", is_superuser=True)
        staff = create_user("staffy", "staffy-pass-1", is_staff=True)
        plain = create_user("plainy", "plainy-pass-1", user_permissions="blog.add_post")
        assert superu.has_perm("anything.at_all") is True
        assert staff.has_perm("blog.view_post") is True
        assert not staff.has_perm("blog.add_post")
        assert plain.has_perm("blog.add_post") is True
        assert not plain.has_perm("blog.delete_post")


class TestAuthenticate:
    def test_valid_credentials(self, auth_env):
        from ronnie.contrib.auth import authenticate

        create_test_user()
        user = authenticate(username="fj", password="s3cret-pass!")
        assert user is not None and user.username == "fj"

    def test_wrong_password(self, auth_env):
        from ronnie.contrib.auth import authenticate

        create_test_user()
        assert authenticate(username="fj", password="nope") is None

    def test_unknown_user(self, auth_env):
        from ronnie.contrib.auth import authenticate

        assert authenticate(username="ghost", password="x") is None


class TestLoginFlow:
    def test_login_redirects_and_authenticates(self, auth_env):
        create_test_user()
        client = make_client()
        response = _login(client, "fj", "s3cret-pass!")
        assert response.status_code == 303
        assert response.headers["location"] == "/"

        protected = client.get("/pages/protected", follow_redirects=False)
        assert protected.status_code == 200
        assert "protected-content" in protected.text

    def test_login_with_next_redirects_there(self, auth_env):
        create_test_user()
        client = make_client()
        response = client.get("/pages/protected", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/accounts/login?next=")

    def test_wrong_password_shows_error(self, auth_env):
        create_test_user()
        client = make_client()
        response = _login(client, "fj", "wrong")
        assert "Invalid username or password" in response.text

    def test_logout_ends_session(self, auth_env):
        create_test_user()
        client = make_client()
        _login(client, "fj", "s3cret-pass!")
        assert "protected-content" in client.get("/pages/protected").text

        logout_page = client.get("/accounts/password_change").text  # any page w/ token
        tag = re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", logout_page)
        token = re.search(r'value="([^"]+)"', tag.group(0)).group(1)
        client.post("/accounts/logout", data={"csrfmiddlewaretoken": token})
        response = client.get("/pages/protected", follow_redirects=False)
        assert response.status_code == 303
        assert "/accounts/login" in response.headers["location"]

    def test_anonymous_auth_param_falsy(self, auth_env):
        client = make_client()
        assert "public-profile" in client.get("/pages/profile").text


class TestPasswordChange:
    def test_change_keeps_session_but_invalidates_others(self, auth_env):
        create_test_user()
        from ronnie.contrib.auth.models import get_user_by_username
        from ronnie.core.passwords import check_password

        client = make_client()
        _login(client, "fj", "s3cret-pass!")

        page = client.get("/accounts/password_change").text
        tag = re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page)
        token = re.search(r'value="([^"]+)"', tag.group(0)).group(1)
        response = client.post(
            "/accounts/password_change",
            data={
                "old_password": "s3cret-pass!",
                "new_password1": "br4nd-new-pass!",
                "new_password2": "br4nd-new-pass!",
                "csrfmiddlewaretoken": token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        # Current session survived (update_session_auth_hash)…
        assert "protected-content" in client.get("/pages/protected").text
        # …and the stored password really changed.
        user = get_user_by_username("fj")
        assert check_password("br4nd-new-pass!", user.password)

    def test_other_sessions_invalidated_by_hash(self, auth_env):
        create_test_user()
        client_a, client_b = make_client(), make_client()
        _login(client_a, "fj", "s3cret-pass!")
        _login(client_b, "fj", "s3cret-pass!")
        assert "protected-content" in client_b.get("/pages/protected").text

        # Change password from A…
        page = client_a.get("/accounts/password_change").text
        token = re.search(
            r'value="([^"]+)"', re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page).group(0)
        ).group(1)
        client_a.post(
            "/accounts/password_change",
            data={
                "old_password": "s3cret-pass!",
                "new_password1": "new-pass-456!",
                "new_password2": "new-pass-456!",
                "csrfmiddlewaretoken": token,
            },
            follow_redirects=False,
        )
        # …B's session must be dead (hash mismatch).
        response = client_b.get("/pages/protected", follow_redirects=False)
        assert response.status_code == 303


class TestCommands:
    def test_createsuperuser_noinput(self, auth_env, monkeypatch):
        monkeypatch.setenv("RONNIE_SUPERUSER_USERNAME", "admin")
        monkeypatch.setenv("RONNIE_SUPERUSER_PASSWORD", "admin-pass-99")
        out = StringIO()
        call_command("createsuperuser", noinput=True, stdout=out)
        assert "admin" in out.getvalue()

        from ronnie.contrib.auth.models import get_user_by_username

        user = get_user_by_username("admin")
        assert user.is_superuser and user.is_staff

    def test_createsuperuser_rejects_weak_password(self, auth_env, monkeypatch):
        monkeypatch.setenv("RONNIE_SUPERUSER_USERNAME", "admin2")
        monkeypatch.setenv("RONNIE_SUPERUSER_PASSWORD", "1234")
        with pytest.raises(CommandError, match=r"numeric|characters"):
            call_command("createsuperuser", noinput=True)

    def test_createsuperuser_duplicate(self, auth_env, monkeypatch):
        create_test_user("taken", "some-pass-123")
        monkeypatch.setenv("RONNIE_SUPERUSER_USERNAME", "taken")
        monkeypatch.setenv("RONNIE_SUPERUSER_PASSWORD", "other-pass-456")
        with pytest.raises(CommandError, match="already taken"):
            call_command("createsuperuser", noinput=True)

    def test_changepassword(self, auth_env, monkeypatch):
        create_test_user()
        monkeypatch.setattr("getpass.getpass", lambda *a: "fresh-pass-789")
        out = StringIO()
        call_command("changepassword", "fj", stdout=out)
        assert "changed" in out.getvalue().lower()

        from ronnie.contrib.auth.models import get_user_by_username
        from ronnie.core.passwords import check_password

        assert check_password("fresh-pass-789", get_user_by_username("fj").password)
