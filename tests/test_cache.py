"""Cache framework tests: shared contract suite + backend specifics (Fase 10)."""

from __future__ import annotations

from typing import Any

import pytest

from ronnie.cache import InvalidCacheBackendError, cache, caches, reset_caches
from ronnie.cache.backends.dummy import DummyCache
from ronnie.cache.backends.filebased import FileBasedCache
from ronnie.cache.backends.locmem import LocMemCache
from ronnie.cache.backends.redis import RedisCache
from ronnie.conf import settings


class FakeRedisCache(RedisCache):
    """RedisCache against fakeredis (dev dependency)."""

    def _create_client(self) -> Any:
        import fakeredis

        return fakeredis.FakeRedis()


def all_backends(tmp_path):
    return [
        LocMemCache({"LOCATION": "test"}),
        FileBasedCache({"LOCATION": str(tmp_path / "fc")}),
        FakeRedisCache({}),
        DummyCache({}),
    ]


CONTRACT_BACKENDS = ["locmem", "filebased", "redis", "dummy"]


@pytest.fixture(params=CONTRACT_BACKENDS)
def backend(request, tmp_path):
    makers = {
        "locmem": lambda: LocMemCache({"LOCATION": "contract"}),
        "filebased": lambda: FileBasedCache({"LOCATION": str(tmp_path / "contract")}),
        "redis": lambda: FakeRedisCache({}),
        "dummy": lambda: DummyCache({}),
    }
    return request.param, makers[request.param]()


@pytest.fixture(autouse=True)
def _cache_settings():
    settings.configure(
        SECRET_KEY="k",
        CACHES={"default": {"BACKEND": "ronnie.cache.backends.locmem.LocMemCache", "LOCATION": "t"}},
    )
    reset_caches()
    yield
    reset_caches()


class TestContract:
    """Every backend honours the same BaseCache contract (dummy excluded for stores)."""

    def test_set_get_roundtrip(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        b.set("k", {"a": [1, 2]}, timeout=60)
        assert b.get("k") == {"a": [1, 2]}

    def test_get_default(self, backend):
        _, b = backend
        assert b.get("missing") is None
        assert b.get("missing", "fallback") == "fallback"

    def test_add_semantics(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        assert b.add("k", 1, timeout=60) is True
        assert b.add("k", 2, timeout=60) is False
        assert b.get("k") == 1

    def test_delete(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        b.set("k", 1, timeout=60)
        assert b.delete("k") is True
        assert b.get("k") is None

    def test_get_or_set(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        assert b.get_or_set("n", lambda: 41 + 1, timeout=60) == 42
        assert b.get_or_set("n", 99, timeout=60) == 42

    def test_many_operations(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        b.set_many({"a": 1, "b": 2}, timeout=60)
        assert b.get_many(["a", "b", "zz"]) == {"a": 1, "b": 2}
        b.delete_many(["a", "b"])
        assert b.get_many(["a", "b"]) == {}

    def test_incr_decr(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        b.set("hits", 10, timeout=60)
        assert b.incr("hits") == 11
        assert b.decr("hits", 5) == 6
        with pytest.raises(ValueError):
            b.incr("never-stored")

    def test_touch(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        b.set("k", "v", timeout=60)
        assert b.touch("k", timeout=60) is True
        assert b.touch("nope") is False

    def test_expiry(self, backend, monkeypatch):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        clock = {"now": 1_000_000.0}
        monkeypatch.setattr(
            __import__("ronnie.cache.backends.locmem", fromlist=["time"]).time, "time", lambda: clock["now"]
        )
        b.set("k", "v", timeout=10)
        clock["now"] += 11
        assert b.get("k") is None

    def test_clear(self, backend):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        b.set("k", 1, timeout=60)
        b.clear()
        assert b.get("k") is None

    def test_key_prefix_and_version(self, backend, tmp_path):
        _, b = backend
        if isinstance(b, DummyCache):
            pytest.skip("dummy stores nothing")
        if isinstance(b, FileBasedCache):
            custom = type(b)({"KEY_PREFIX": "app", "VERSION": 2, "LOCATION": str(tmp_path / "pv")})
        elif isinstance(b, FakeRedisCache):
            custom = FakeRedisCache({"KEY_PREFIX": "app", "VERSION": 2})
        else:
            custom = type(b)({"KEY_PREFIX": "app", "VERSION": 2, "LOCATION": "x"})
        custom.set("k", "v", timeout=60)
        assert custom.get("k", version=2) == "v"
        assert custom.get("k", version=1) is None


class TestCachesHandler:
    def test_default_alias(self):
        caches["default"].set("x", 1, timeout=10)
        assert cache.get("x") == 1  # proxy → default

    def test_unknown_alias_rejected(self):
        with pytest.raises(InvalidCacheBackendError):
            caches["nope"]

    def test_custom_backend_config(self):
        settings.CACHES = {
            "default": {"BACKEND": "ronnie.cache.backends.dummy.DummyCache"},
            "files": {"BACKEND": "ronnie.cache.backends.locmem.LocMemCache"},
        }
        reset_caches()
        caches["files"].set("y", 2, timeout=10)
        assert caches["files"].get("y") == 2
        assert caches["default"].get("y") is None


class TestLocMemSpecifics:
    def test_cull_on_overflow(self):
        b = LocMemCache({"LOCATION": "cull", "OPTIONS": {"MAX_ENTRIES": 10, "CULL_FREQUENCY": 2}})
        for i in range(20):
            b.set(f"k{i}", i, timeout=60)
        assert len(b._store) <= 10

    def test_thread_safety_smoke(self):
        import threading

        b = LocMemCache({"LOCATION": "threads"})
        errors = []

        def worker(n: int) -> None:
            try:
                for i in range(100):
                    b.set(f"t{n}-{i}", i, timeout=60)
                    b.get(f"t{n}-{i}")
            except Exception as err:
                errors.append(err)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestFileBasedSpecifics:
    def test_files_created_and_removed(self, tmp_path):
        b = FileBasedCache({"LOCATION": str(tmp_path / "fb")})
        b.set("k", "v", timeout=60)
        files = list((tmp_path / "fb").glob("ronnie-cache-*.cache"))
        assert len(files) == 1
        b.delete("k")
        assert not list((tmp_path / "fb").glob("ronnie-cache-*.cache"))

    def test_corrupted_file_treated_as_miss(self, tmp_path):
        b = FileBasedCache({"LOCATION": str(tmp_path / "fb2")})
        b.set("k", "v", timeout=60)
        for path in (tmp_path / "fb2").glob("*.cache"):
            path.write_bytes(b"garbage")
        assert b.get("k") is None


class TestHttpHelpers:
    def test_cache_page_decorator(self, monkeypatch):
        from fasthtml.common import P

        from ronnie.cache.http import cache_page

        calls = {"n": 0}

        class FakeRequest:
            method = "GET"
            url = type("U", (), {"path": "/x"})()

            def __init__(self) -> None:
                self.query_params: dict = {}

        @cache_page(60)
        def view(req):
            calls["n"] += 1
            return P(f"call-{calls['n']}")

        first = view(req=FakeRequest())
        view(req=FakeRequest())
        assert calls["n"] == 1  # second hit served from cache
        assert first is not None

    def test_cache_page_bypasses_post(self):
        from ronnie.cache.http import cache_page

        class FakeRequest:
            method = "POST"
            url = type("U", (), {"path": "/x"})()

            def __init__(self) -> None:
                self.query_params: dict = {}

        @cache_page(60)
        def view(req):
            return "written"

        assert view(req=FakeRequest()) == "written"

    def test_cache_fragment(self):
        from fasthtml.common import Li, Ul

        from ronnie.cache.http import cache_fragment, make_fragment_key

        calls = {"n": 0}

        def build():
            calls["n"] += 1
            return Ul(Li("x"))

        key = make_fragment_key("list", ["user1"])
        first = cache_fragment(key, 60, build)
        second = cache_fragment(key, 60, build)
        assert calls["n"] == 1
        assert first == second and "<li>x</li>" in first

    def test_cache_middleware_e2e(self, tmp_path):
        from starlette.testclient import TestClient

        from ronnie.core.asgi import get_asgi_application

        settings.MIDDLEWARE = ["ronnie.cache.http.CacheMiddleware"]
        settings.INSTALLED_APPS = ["apps.pages"]
        from ronnie.apps import apps

        apps.clear_data()
        import ronnie

        ronnie.setup()
        with TestClient(get_asgi_application()) as client:
            first = client.get("/pages/")
            second = client.get("/pages/")
            assert first.status_code == second.status_code == 200
            assert first.text == second.text
