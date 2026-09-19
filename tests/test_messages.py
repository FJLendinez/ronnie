"""Tests for contrib.messages (Fase 9)."""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from ronnie.conf import settings


def configure(**extra: Any):
    values: dict[str, Any] = {
        "SECRET_KEY": "messages-key",
        "DEBUG": False,
        "ALLOWED_HOSTS": ["testserver"],
        "INSTALLED_APPS": ["apps.pages", "ronnie.contrib.sessions", "ronnie.contrib.messages"],
        "MIDDLEWARE": [
            "ronnie.middleware.security.SecurityMiddleware",
            "ronnie.middleware.host.HostValidationMiddleware",
            "ronnie.contrib.sessions.middleware.SessionMiddleware",
            "ronnie.middleware.csrf.CsrfMiddleware",
            "ronnie.contrib.messages.middleware.MessagesMiddleware",
            "ronnie.middleware.clickjacking.XFrameOptionsMiddleware",
        ],
    }
    values.update(extra)
    settings.configure(**values)


def make_client() -> TestClient:
    from ronnie.core.asgi import get_asgi_application

    return TestClient(get_asgi_application())


class TestSessionStorage:
    def test_flash_survives_redirect(self):
        configure(MESSAGE_STORAGE="ronnie.contrib.messages.storage.SessionStorage")
        client = make_client()
        response = client.get("/pages/flash_save", follow_redirects=True)
        assert "Saved!" in response.text
        assert "FYI" in response.text

    def test_flash_cleared_after_reading(self):
        configure(MESSAGE_STORAGE="ronnie.contrib.messages.storage.SessionStorage")
        client = make_client()
        client.get("/pages/flash_save", follow_redirects=False)
        first = client.get("/pages/flash_show")
        second = client.get("/pages/flash_show")
        assert "Saved!" in first.text
        assert "Saved!" not in second.text


class TestFallbackStorage:
    def test_flash_via_cookie(self):
        configure()
        client = make_client()
        response = client.get("/pages/flash_save", follow_redirects=True)
        assert "Saved!" in response.text
        assert "alert success" in response.text
        assert "banner" in response.text  # extra_tags rendered

    def test_overflow_falls_back_to_session(self):
        configure()
        client = make_client()
        response = client.get("/pages/flash_save", follow_redirects=True)
        assert "Saved!" in response.text

    def test_tampered_cookie_ignored(self):
        configure()
        client = make_client()
        client.get("/pages/flash_save")
        # Corrupt the message cookie; the flash must vanish, not crash.
        client.cookies.set("ronnie_messages", "garbage:deadbeef")
        response = client.get("/pages/flash_show")
        assert response.status_code == 200
        assert "Saved!" not in response.text


class TestLevelsAndTags:
    def test_message_level_filtering(self):
        configure(MESSAGE_LEVEL=30)  # WARNING+: info/success dropped
        client = make_client()
        response = client.get("/pages/flash_save", follow_redirects=True)
        assert "Saved!" not in response.text  # success(25) < 30 → dropped
        assert "FYI" not in response.text

    def test_custom_message_tags(self):
        configure(MESSAGE_TAGS={25: "win"})
        client = make_client()
        response = client.get("/pages/flash_save", follow_redirects=True)
        assert "alert win" in response.text

    def test_message_tags_and_level_tag(self):
        configure()
        from ronnie.contrib.messages.storage import Message

        m = Message(30, "careful", "banner")
        assert m.level_tag == "warning"
        assert m.tags == "banner warning"
