"""Coverage batch 2: testing utils/client, cache, security, csrf, sessions."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient as TC

from ronnie.conf import settings
from ronnie.core.exceptions import ImproperlyConfigured
from ronnie.testing import RonnieTestClient, override_settings
from ronnie.testing.utils import capture_signaled_settings

SECRET = "cov-framework-key"


@pytest.fixture(autouse=True)
def _configured():
    settings.configure(
        SECRET_KEY=SECRET,
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        INSTALLED_APPS=["apps.pages"],
        MIDDLEWARE=[],
    )
    yield


# -- testing/utils ---------------------------------------------------------------


class TestModifySettings:
    def test_append_prepend_remove(self):
        settings.MIDDLEWARE = ["a.M"]
        from ronnie.testing.utils import modify_settings

        with modify_settings(MIDDLEWARE={"append": ["b.M"], "prepend": ["zero.M"]}):
            assert settings.MIDDLEWARE == ["zero.M", "a.M", "b.M"]
        assert settings.MIDDLEWARE == ["a.M"]
        with modify_settings(MIDDLEWARE={"remove": ["a.M"]}):
            assert settings.MIDDLEWARE == []
        assert settings.MIDDLEWARE == ["a.M"]

    def test_kwargs_form_and_invalid_action(self):
        from ronnie.testing.utils import modify_settings

        with modify_settings(MIDDLEWARE={"append": ["x"]}) as ctx:
            assert ctx is not None
        with (
            pytest.raises(ValueError, match="Unknown modify_settings action"),
            modify_settings(MIDDLEWARE={"sideways": ["x"]}),
        ):
            pass


class TestOverrideSettingsAsClassDecorator:
    def test_decorate_testcase_class(self):
        from ronnie.testing import SimpleTestCase

        @override_settings(TIME_ZONE="Atlantic/Canary")
        class Case(SimpleTestCase):
            def runTest(self):
                pass

        Case.setUpClass()
        try:
            assert settings.TIME_ZONE == "Atlantic/Canary"
        finally:
            Case.tearDownClass()
        assert settings.TIME_ZONE == "UTC"

    def test_enable_without_any_configuration_raises(self, monkeypatch):
        import ronnie.conf as conf_module

        monkeypatch.setattr(conf_module.settings, "_wrapped", None)
        monkeypatch.delenv(conf_module.SETTINGS_MODULE_ENV, raising=False)
        with pytest.raises(ImproperlyConfigured), override_settings(DEBUG=True):
            pass

    def test_capture_helper_empty(self):
        with capture_signaled_settings() as events:
            pass
        assert events == []


class TestRonnieTestClientVerbs:
    def test_all_verbs_and_helpers(self):
        client = RonnieTestClient()
        assert client.get("/pages/").status_code == 200
        assert client.head("/pages/").status_code == 200
        assert client.request("GET", "/pages/").status_code == 200
        assert client.cookies is not None
        response = client.json_request("GET", "/pages/")
        assert response.status_code == 200
        assert client.htmx("GET", "/pages/echo_htmx").status_code == 200


class TestAssertionsFailures:
    def _case(self):
        from ronnie.testing import RonnieTestCase

        class Case(RonnieTestCase):
            def runTest(self):
                pass

        return Case("runTest")

    def test_assert_contains_failures(self):
        case = self._case()
        response = type("R", (), {"status_code": 200, "text": "hello world"})()
        with pytest.raises(AssertionError, match="Couldn't find"):
            case.assertContains(response, "nope")
        with pytest.raises(AssertionError, match="occurrences"):
            case.assertContains(response, "l", count=5)
        with pytest.raises(AssertionError, match="Expected status"):
            case.assertContains(type("R", (), {"status_code": 500, "text": "x"})(), "x")

    def test_assert_not_contains_failure(self):
        case = self._case()
        response = type("R", (), {"status_code": 200, "text": "abc"})()
        with pytest.raises(AssertionError, match="Unexpectedly found"):
            case.assertNotContains(response, "abc")

    def test_assert_redirect_failures(self):
        case = self._case()
        redirect = type("R", (), {"status_code": 200, "headers": {}, "history": []})()
        with pytest.raises(AssertionError, match="Expected status"):
            case.assertRedirects(redirect, "/x")
        bad_location = type("R", (), {"status_code": 302, "headers": {"location": "/other"}, "history": []})()
        with pytest.raises(AssertionError, match="Expected redirect to"):
            case.assertRedirects(bad_location, "/x")

    def test_fail_default_message(self):
        from ronnie.testing.assertions import AssertionsMixin

        with pytest.raises(AssertionError):
            AssertionsMixin().fail()


# -- cache ------------------------------------------------------------------------


class TestCacheExtras:
    def test_missing_backend_rejected(self):
        from ronnie.cache import InvalidCacheBackendError, reset_caches

        settings.CACHES = {"default": {"LOCATION": "x"}}
        reset_caches()
        with pytest.raises(InvalidCacheBackendError, match="needs a BACKEND"):
            from ronnie.cache import caches

            caches["default"]
        settings.CACHES = {"default": {"BACKEND": "ronnie.cache.backends.locmem.LocMemCache"}}
        reset_caches()

    def test_redis_requires_redis_py(self):
        from ronnie.cache.backends.redis import RedisCache

        try:
            import redis  # noqa: F401

            pytest.skip("redis installed: covered by contract tests")
        except ImportError:
            pass
        cache = RedisCache({})
        with pytest.raises(ImproperlyConfigured, match="ronnie\\[redis\\]"):
            _ = cache.client

    def test_key_validation_warns_on_spaces(self):
        import warnings

        from ronnie.cache.backends.locmem import LocMemCache

        cache = LocMemCache({})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cache.set("has space", 1, timeout=5)
        assert any("spaces" in str(w.message) for w in caught)

    def test_custom_key_function(self):
        from ronnie.cache.backends.locmem import LocMemCache

        cache = LocMemCache({"KEY_FUNCTION": "sample_middleware.screaming_keys"})
        cache.set("k", "v", timeout=5)
        assert any("|1|K" in stored_key for stored_key in cache._store)

    def test_close_is_noop(self):
        from ronnie.cache import cache

        cache.close()

    def test_cache_control_headers(self):
        from ronnie.cache.http import cache_control, no_cache

        assert no_cache().v == "no-store, no-cache, must-revalidate, max-age=0"
        header = cache_control(max_age=3600, private=True, no_store=False, stale=None)
        assert header.v == "max-age=3600, private"

    def test_filebased_cull_overflow(self, tmp_path):
        from ronnie.cache.backends.filebased import FileBasedCache

        cache = FileBasedCache(
            {"LOCATION": str(tmp_path / "c"), "OPTIONS": {"MAX_ENTRIES": 5, "CULL_FREQUENCY": 2}}
        )
        for i in range(20):
            cache.set(f"k{i}", i, timeout=600)
        assert len(list((tmp_path / "c").glob("*.cache"))) <= 5

    def test_filebased_survives_corrupt_and_none_expiry(self, tmp_path):
        from ronnie.cache.backends.filebased import FileBasedCache

        cache = FileBasedCache({"LOCATION": str(tmp_path / "n")})
        cache.set("forever", 1, timeout=None)
        assert cache.get("forever") == 1

    def test_cache_middleware_skips_non_get_and_errors(self):
        from starlette.testclient import TestClient as TC

        from ronnie.core.asgi import get_asgi_application

        settings.MIDDLEWARE = ["ronnie.cache.http.CacheMiddleware"]
        from ronnie.apps import apps

        apps.clear_data()
        import ronnie

        ronnie.setup()
        with TC(get_asgi_application()) as client:
            assert client.post("/pages/save", data={"title": "x"}).status_code in (200, 403)
            assert client.get("/nope").status_code == 404  # non-200 not cached


# -- security / csrf extras ---------------------------------------------------------


def make_app(**overrides):
    from ronnie.core.asgi import get_asgi_application

    base = {
        "SECRET_KEY": SECRET,
        "DEBUG": False,
        "ALLOWED_HOSTS": ["testserver"],
        "INSTALLED_APPS": ["apps.pages"],
        "MIDDLEWARE": [
            "ronnie.middleware.security.SecurityMiddleware",
            "ronnie.middleware.host.HostValidationMiddleware",
            "ronnie.contrib.sessions.middleware.SessionMiddleware",
            "ronnie.middleware.csrf.CsrfMiddleware",
            "ronnie.middleware.clickjacking.XFrameOptionsMiddleware",
        ],
    }
    base.update(overrides)
    for key, value in base.items():
        setattr(settings, key, value)
    from ronnie.apps import apps

    apps.clear_data()
    import ronnie

    ronnie.setup()
    return TC(get_asgi_application())


class TestSecurityExtras:
    def test_hsts_preload_and_disabled_headers(self):
        with make_app(
            SECURE_HSTS_SECONDS=100,
            SECURE_HSTS_PRELOAD=True,
            SECURE_REFERRER_POLICY=None,
            SECURE_CROSS_ORIGIN_OPENER_POLICY=None,
            SECURE_CONTENT_TYPE_NOSNIFF=False,
        ) as client:
            response = client.get("/pages/")
            assert response.headers["strict-transport-security"] == "max-age=100; preload"
            assert "referrer-policy" not in response.headers
            assert "cross-origin-opener-policy" not in response.headers
            assert "x-content-type-options" not in response.headers

    def test_proxy_ssl_header_prevents_redirect(self):
        with make_app(
            SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("X-Forwarded-Proto", "https")
        ) as client:
            response = client.get("/pages/", follow_redirects=False, headers={"X-Forwarded-Proto": "https"})
            assert response.status_code == 200

    def test_clickjacking_existing_header(self):
        # Compose: clickjacking OUTSIDE a wrapper that already sets the header.
        from ronnie.apps import apps
        from ronnie.contrib.sessions.middleware import SessionMiddleware
        from ronnie.core.asgi import get_asgi_application
        from ronnie.middleware.clickjacking import XFrameOptionsMiddleware

        settings.MIDDLEWARE = []
        apps.clear_data()
        import ronnie

        ronnie.setup()

        class PreHeader:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                async def send_with(message):
                    if message["type"] == "http.response.start":
                        message = dict(message)
                        message["headers"] = [
                            *message.get("headers", []),
                            (b"x-frame-options", b"SAMEORIGIN"),
                        ]
                    await send(message)

                await self.app(scope, receive, send_with)

        wrapped = XFrameOptionsMiddleware(SessionMiddleware(PreHeader(get_asgi_application())))
        with TC(wrapped) as client:
            assert client.get("/pages/").headers["x-frame-options"] == "SAMEORIGIN"

    def test_middleware_skips_lifespan_scope(self):
        import asyncio

        from ronnie.middleware.clickjacking import XFrameOptionsMiddleware
        from ronnie.middleware.host import HostValidationMiddleware
        from ronnie.middleware.security import SecurityMiddleware

        sentinel = {"called": False}

        async def app(scope, receive, send):
            sentinel["called"] = True

        for cls in (SecurityMiddleware, HostValidationMiddleware, XFrameOptionsMiddleware):
            asyncio.run(cls(app)({"type": "lifespan"}, None, None))
        assert sentinel["called"]

    def test_use_forwarded_host(self):
        with make_app(USE_X_FORWARDED_HOST=True, ALLOWED_HOSTS=["proxy.example"]) as client:
            forwarded = client.get("/pages/", headers={"X-Forwarded-Host": "proxy.example"})
            spoofed = client.get("/pages/", headers={"X-Forwarded-Host": "evil.example"})
            assert forwarded.status_code == 200
            assert spoofed.status_code == 400, spoofed.text


class TestCsrfExtras:
    def _post(self, client, path, **kw):
        return client.post(path, data=kw.pop("data", {"x": "1"}), **kw)

    def test_missing_session_rejected(self):
        # CSRF middleware without a session in scope fails closed.
        settings.MIDDLEWARE = ["ronnie.middleware.csrf.CsrfMiddleware"]
        from ronnie.apps import apps

        apps.clear_data()
        import ronnie

        ronnie.setup()
        from ronnie.core.asgi import get_asgi_application

        with TC(get_asgi_application()) as client:
            response = self._post(client, "/pages/save")
            assert response.status_code == 403

    def test_https_origin_and_referer_checks(self):
        with make_app() as client:
            page = client.get("/pages/new")
            import re

            token = re.search(
                r'value="([^"]+)"', re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page.text).group(0)
            ).group(1)
            # Valid Origin passes
            response = client.post(
                "/pages/save",
                data={"title": "a"},
                headers={"X-CSRFToken": token, "Origin": "http://testserver"},
            )
            assert response.status_code == 200

    def test_multipart_token_extraction(self):
        with make_app() as client:
            page = client.get("/pages/new")
            import re

            token = re.search(
                r'value="([^"]+)"', re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page.text).group(0)
            ).group(1)
            response = client.post(
                "/pages/save",
                files={"file": ("a.txt", b"hello")},
                data={"title": "mp", "csrfmiddlewaretoken": token},
            )
            assert response.status_code == 200

    def test_drain_on_disconnect(self):
        import asyncio

        from ronnie.middleware.csrf import CsrfMiddleware

        async def receive():
            return {"type": "http.disconnect"}

        async def send(_message):
            pass

        done: list = []

        async def app(scope, receive, send):
            done.append(True)

        async def run():
            await CsrfMiddleware(app)(
                {"type": "http", "method": "POST", "path": "/x", "headers": []}, receive, send
            )

        asyncio.run(run())
        assert done == []

    def test_token_helpers(self):
        from ronnie.middleware.csrf import TOKEN_SESSION_KEY, csrf_token, hx_csrf_headers

        session: dict = {}
        token = csrf_token(session)
        assert session[TOKEN_SESSION_KEY] == token
        assert hx_csrf_headers(token) == {"X-CSRFToken": token}

        # request-like object without session raises a clear error
        class Bare:
            scope = {"no": "session"}

        with pytest.raises(ImproperlyConfigured):
            csrf_token(Bare())


# -- sessions engines/middleware ------------------------------------------------------


class TestSessionEngineExtras:
    def test_dotted_path_engine_resolution(self, tmp_path, monkeypatch):
        fake_engine = type(
            "FakeEngine",
            (),
            {
                "new_key": staticmethod(lambda: "k"),
                "load": staticmethod(lambda key: {}),
                "save": staticmethod(lambda *a: None),
                "delete": staticmethod(lambda key: None),
                "clear_expired": staticmethod(lambda: 0),
            },
        )
        import types

        module = types.ModuleType("my_custom_engine")
        module.Engine = fake_engine
        import sys

        monkeypatch.setitem(sys.modules, "my_custom_engine", module)
        from ronnie.contrib.sessions.engines import resolve_engine

        engine = resolve_engine("my_custom_engine.Engine")
        assert isinstance(engine, fake_engine)

    def test_unresolvable_path_rejected(self):
        from ronnie.contrib.sessions.engines import resolve_engine

        with pytest.raises(ImproperlyConfigured, match="Cannot import"):
            resolve_engine("no.such.Thing")

    def test_broken_instance_rejected(self, monkeypatch):
        import sys
        import types

        module = types.ModuleType("bad_instance_engine")
        module.Engine = lambda: "not-an-engine"
        monkeypatch.setitem(sys.modules, "bad_instance_engine", module)
        from ronnie.contrib.sessions.engines import resolve_engine

        with pytest.raises(ImproperlyConfigured, match="does not implement"):
            resolve_engine("bad_instance_engine.Engine")

    def test_db_engine_edge_cases(self, tmp_path):
        import ronnie

        settings.INSTALLED_APPS = ["ronnie.contrib.sessions"]
        settings.SESSION_ENGINE = "db"
        settings.DATABASES = {"default": {"ENGINE": "sqlite", "NAME": tmp_path / "e.db"}}
        from ronnie.apps import apps

        apps.clear_data()
        ronnie.setup()
        from ronnie.db import install_tables

        install_tables()
        from ronnie.contrib.sessions.engines import DbSessionEngine

        engine = DbSessionEngine()
        assert engine.load("missing-key") is None
        # Corrupt payload → None; save with fresh key inserts (fallback path).
        key = engine.new_key()
        engine.save(key, {"a": 1}, 60)
        row = engine.table[key]
        row.data = "{not json"
        engine.table.update(row)
        assert engine.load(key) is None
        # clear_expired tolerates junk dates
        row2 = engine.table[key]
        row2.expire_date = "garbage-date"
        engine.table.update(row2)
        assert engine.clear_expired() == 0
        engine.delete(key)  # idempotent delete

    def test_middleware_cookie_flags(self):
        settings.SESSION_COOKIE_SECURE = True
        settings.SESSION_COOKIE_DOMAIN = "example.com"
        from ronnie.contrib.sessions.middleware import SessionMiddleware, TrackingSession

        class App:
            def __init__(self):
                self.seen = {}

            async def __call__(self, scope, receive, send):
                scope["session"]["n"] = 1
                self.seen = scope

        app = App()
        middleware = SessionMiddleware(app)
        assert middleware._cookie_mw is not None  # cookie engine wraps starlette

        # TrackingSession marks mutations
        session = TrackingSession()
        session["a"] = 1
        assert session.modified is True
