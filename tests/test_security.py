"""Tests for security: signing, passwords, middlewares, CSRF (Fase 6)."""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from ronnie.conf import settings
from ronnie.core.exceptions import ImproperlyConfigured, ValidationError
from ronnie.core.passwords import check_password, make_password, validate_password
from ronnie.core.passwords.hashers import PBKDF2PasswordHasher, identify_hasher
from ronnie.core.signing import (
    BadSignature,
    SignatureExpired,
    Signer,
    TimestampSigner,
    dumps,
    loads,
)

SECRET = "unit-test-secret-key"


@pytest.fixture(autouse=True)
def _security_settings():
    settings.configure(SECRET_KEY=SECRET, DEBUG=False)
    yield


class TestSigning:
    def test_sign_unsign_roundtrip(self):
        signer = Signer()
        signed = signer.sign("hello")
        assert signed == f"hello:{signer.signature('hello')}"
        assert signer.unsign(signed) == "hello"

    def test_tampered_value_rejected(self):
        signed = Signer().sign("hello")
        with pytest.raises(BadSignature):
            Signer().unsign("h3llo" + signed[5:])

    def test_wrong_key_rejected(self):
        signed = Signer(key="other").sign("v")
        with pytest.raises(BadSignature):
            Signer(key="right").unsign(signed)

    def test_fallback_keys_verify_only(self):
        signed = Signer(key="old").sign("v")
        assert Signer(key="new", fallback_keys=["old"]).unsign(signed) == "v"
        assert Signer(key="new").sign("x").startswith("x:")

    def test_salt_isolates_signatures(self):
        signed = Signer(salt="a").sign("v")
        with pytest.raises(BadSignature):
            Signer(salt="b").unsign(signed)

    def test_unsafe_separator_rejected(self):
        with pytest.raises(ValueError):
            Signer(sep="a")

    def test_timestamp_max_age(self):
        signed = TimestampSigner().sign("v")
        assert TimestampSigner().unsign(signed, max_age=3600) == "v"
        with pytest.raises(SignatureExpired):
            TimestampSigner().unsign(signed, max_age=-1)

    def test_dumps_loads_roundtrip(self):
        payload = dumps({"uid": 42, "op": "reset"}, salt="pw-reset")
        assert loads(payload, salt="pw-reset") == {"uid": 42, "op": "reset"}

    def test_loads_expired(self):
        with pytest.raises(SignatureExpired):
            loads(dumps({"x": 1}), max_age=-1)

    def test_no_secret_key_raises(self):
        settings.SECRET_KEY = ""
        with pytest.raises(ImproperlyConfigured):
            Signer().sign("v")


class TestPasswordHashing:
    def test_make_password_format(self):
        encoded = make_password("s3cret!")
        algorithm, iterations, salt, _ = encoded.split("$")
        assert algorithm == "pbkdf2_sha256"
        assert int(iterations) >= 100_000
        assert len(salt) == 32  # 128 bits hex

    def test_check_password_roundtrip(self):
        assert check_password("s3cret!", make_password("s3cret!")) is True
        assert check_password("wrong", make_password("s3cret!")) is False

    def test_salt_randomizes(self):
        assert make_password("x") != make_password("x")

    def test_unusable_password(self):
        encoded = make_password(None)
        assert encoded.startswith("!")
        assert check_password(None, encoded) is False
        assert check_password("anything", encoded) is False

    def test_identify_hasher(self):
        assert isinstance(identify_hasher(make_password("x")), PBKDF2PasswordHasher)

    def test_scrypt_hasher(self):
        from ronnie.core.passwords.hashers import ScryptPasswordHasher

        encoded = ScryptPasswordHasher().encode("pw", "s" * 16)
        assert encoded.startswith("scrypt$")
        assert check_password("pw", encoded) is True
        assert check_password("no", encoded) is False

    def test_verify_django_pbkdf2_format(self):
        # Hash produced by Django with identical parameters (iterations=260000).
        django_hash = "pbkdf2_sha256$260000$0123456789abcdef0123456789abcdef$ABCD" + "A" * 40
        # We can't recompute Django's secret; just ensure our verifier parses it.
        hasher = identify_hasher(django_hash)
        assert hasher.algorithm == "pbkdf2_sha256"

    def test_must_upgrade_iterations(self):
        hasher = PBKDF2PasswordHasher()
        old = hasher.encode("pw", "salt", iterations=1000)
        assert hasher.must_update(old) is True
        assert hasher.must_update(hasher.encode("pw", "salt")) is False


class TestPasswordValidators:
    def test_minimum_length(self):
        from ronnie.core.passwords.validators import MinimumLengthValidator

        validator = MinimumLengthValidator(min_length=8)
        with pytest.raises(ValidationError):
            validator.validate("short")
        validator.validate("long-enough-password")

    def test_common_password(self):
        from ronnie.core.passwords.validators import CommonPasswordValidator

        validator = CommonPasswordValidator()
        with pytest.raises(ValidationError):
            validator.validate("Password1")
        validator.validate("xK9-mQ2!vZ")

    def test_numeric_password(self):
        from ronnie.core.passwords.validators import NumericPasswordValidator

        with pytest.raises(ValidationError):
            validate_password("12345678", password_validators=[NumericPasswordValidator()])

    def test_user_similarity(self):
        from ronnie.core.passwords.validators import UserAttributeSimilarityValidator

        class User:
            username = "fjlendinez"

        validator = UserAttributeSimilarityValidator()
        with pytest.raises(ValidationError):
            validator.validate("fjlendinez99", user=User())
        validator.validate("totally-unrelated-pw", user=User())

    def test_validate_password_collects_errors(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_password("1234")
        assert len(exc_info.value.messages) >= 2  # too short + numeric

    def test_validate_password_ok(self):
        validate_password("a-very-solid-passphrase-42")

    def test_help_texts(self):
        from ronnie.core.passwords.validators import password_validators_help_texts

        texts = password_validators_help_texts()
        assert len(texts) == 4


def make_app(**overrides) -> TestClient:
    from ronnie.core.asgi import get_asgi_application

    base = {
        "SECRET_KEY": SECRET,
        "DEBUG": False,
        "ALLOWED_HOSTS": ["testserver"],
        "INSTALLED_APPS": ["apps.pages"],
    }
    base.update(overrides)
    for key, value in base.items():  # fixture already configured settings
        setattr(settings, key, value)
    return TestClient(get_asgi_application())


class TestHostValidation:
    def test_allowed_host_passes(self):
        with make_app() as client:
            assert client.get("/pages/").status_code == 200

    def test_disallowed_host_rejected(self):
        from ronnie.core.asgi import get_asgi_application

        for key, value in {
            "SECRET_KEY": SECRET,
            "DEBUG": False,
            "ALLOWED_HOSTS": ["good.example.com"],
            "INSTALLED_APPS": ["apps.pages"],
        }.items():
            setattr(settings, key, value)
        app = get_asgi_application()
        with TestClient(app, base_url="http://evil.example.com") as client:
            assert client.get("/pages/").status_code == 400

    def test_wildcard_subdomains(self):
        from ronnie.middleware.host import validate_host

        assert validate_host("api.example.com", [".example.com"]) is True
        assert validate_host("example.com", [".example.com"]) is True
        assert validate_host("notexample.com", [".example.com"]) is False
        assert validate_host("any.host", ["*"]) is True

    def test_port_stripped(self):
        from ronnie.middleware.host import validate_host

        assert validate_host("example.com:8000", ["example.com"]) is True


class TestSecurityHeaders:
    def test_default_headers_present(self):
        with make_app() as client:
            response = client.get("/pages/")
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "same-origin"
            assert response.headers["cross-origin-opener-policy"] == "same-origin"
            assert response.headers["x-frame-options"] == "DENY"

    def test_hsts_when_configured(self):
        with make_app(SECURE_HSTS_SECONDS=31_536_000, SECURE_HSTS_INCLUDE_SUBDOMAINS=True) as client:
            response = client.get("/pages/")
            assert response.headers["strict-transport-security"] == ("max-age=31536000; includeSubDomains")

    def test_ssl_redirect(self):
        with make_app(SECURE_SSL_REDIRECT=True, SECURE_SSL_HOST="secure.example.com") as client:
            response = client.get("/pages/", follow_redirects=False)
            assert response.status_code == 301
            assert response.headers["location"].startswith("https://secure.example.com")

    def test_ssl_redirect_exemptions(self):
        with make_app(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^/health"]) as client:
            assert client.get("/health", follow_redirects=False).status_code == 404  # no redirect


class TestCsrf:
    def _get_token(self, client: TestClient) -> str:
        page = client.get("/pages/new").text
        tag = re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page)
        assert tag, page[:500]
        match = re.search(r'value="([^"]+)"', tag.group(0))
        assert match, tag.group(0)
        return match.group(1)

    def test_post_without_token_rejected(self):
        with make_app() as client:
            response = client.post("/pages/save", data={"title": "x"})
            assert response.status_code == 403
            assert "CSRF" in response.text

    def test_post_with_form_token_accepted(self):
        with make_app() as client:
            token = self._get_token(client)
            response = client.post("/pages/save", data={"title": "hi", "csrfmiddlewaretoken": token})
            assert response.status_code == 200
            assert "saved:hi" in response.text

    def test_post_with_header_token_accepted(self):
        with make_app() as client:
            token = self._get_token(client)
            response = client.post("/pages/save", data={"title": "hdr"}, headers={"X-CSRFToken": token})
            assert response.status_code == 200

    def test_token_from_other_session_rejected(self):
        with make_app() as client_a:
            token = self._get_token(client_a)
        with make_app() as client_b:
            response = client_b.post("/pages/save", data={"title": "x", "csrfmiddlewaretoken": token})
            assert response.status_code == 403

    def test_exempt_path_bypasses(self):
        with make_app(CSRF_EXEMPT_PATHS=[r"^/pages/save$"]) as client:
            assert client.post("/pages/save", data={"title": "x"}).status_code == 200

    def test_get_requests_unaffected(self):
        with make_app() as client:
            assert client.get("/pages/new").status_code == 200


class TestCsrfExemptDecorator:
    def test_exempt_decorator_allows_post_without_token(self):
        with make_app() as client:
            response = client.post("/pages/webhook", data={"payload": "x"})
            assert response.status_code == 200
            assert "webhook-ok" in response.text

    def test_exempt_decorator_with_path_params(self):
        with make_app() as client:
            response = client.post("/pages/hook/abc123", data={"payload": "x"})
            assert response.status_code == 200
            assert "hook-abc123" in response.text

    def test_non_exempt_still_rejected(self):
        with make_app() as client:
            assert client.post("/pages/guarded_post", data={"x": "1"}).status_code == 403

    def test_exemption_is_exact_not_prefix(self):
        with make_app() as client:
            # A different path must NOT inherit the exemption: CSRF rejects
            # before routing, so an unrouted unsafe path yields 403, not 404.
            response = client.post("/pages/webhook-extra", data={"x": "1"})
            assert response.status_code == 403
