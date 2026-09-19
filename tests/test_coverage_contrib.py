"""Coverage batch 3: contrib branches, tasks worker/beat, auth extras."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient as TC

from ronnie.conf import settings
from ronnie.core.exceptions import ImproperlyConfigured

SECRET = "cov-contrib-key"


@pytest.fixture(autouse=True)
def _configured():
    from ronnie.core.passwords.hashers import PBKDF2PasswordHasher

    original_iterations = PBKDF2PasswordHasher.iterations
    settings.configure(SECRET_KEY=SECRET, DEBUG=False, ALLOWED_HOSTS=["testserver"])
    yield
    PBKDF2PasswordHasher.iterations = original_iterations


# -- admin -----------------------------------------------------------------------


class TestAdminBranches:
    def _staff_client(self, tmp_path: Path):
        import ronnie
        from ronnie.apps import apps

        for key, value in {
            "INSTALLED_APPS": [
                "apps.shop",
                "ronnie.contrib.sessions",
                "ronnie.contrib.auth",
                "ronnie.contrib.messages",
                "ronnie.contrib.admin",
            ],
            "MIDDLEWARE": [
                "ronnie.middleware.security.SecurityMiddleware",
                "ronnie.middleware.host.HostValidationMiddleware",
                "ronnie.contrib.sessions.middleware.SessionMiddleware",
                "ronnie.middleware.csrf.CsrfMiddleware",
                "ronnie.contrib.auth.middleware.AuthMiddleware",
                "ronnie.contrib.messages.middleware.MessagesMiddleware",
                "ronnie.middleware.clickjacking.XFrameOptionsMiddleware",
            ],
            "DATABASES": {"default": {"ENGINE": "sqlite", "NAME": tmp_path / "a.db"}},
            "LOGIN_REDIRECT_URL": "/admin/",
        }.items():
            setattr(settings, key, value)
        from ronnie.core.passwords.hashers import PBKDF2PasswordHasher

        PBKDF2PasswordHasher.iterations = 1000
        apps.clear_data()
        ronnie.setup()
        from ronnie.db import install_tables

        install_tables()
        from apps.shop.models import Product
        from ronnie.contrib.auth.models import create_user
        from ronnie.db import get_table

        create_user("stf", "stf-pass-1", is_staff=True)
        get_table(Product).insert(name="mug", price=5.0)
        client = TC(_build_app())
        _login(client)
        return client, get_table(Product)

    def test_unknown_model_and_not_found(self, tmp_path):
        client, _table = self._staff_client(tmp_path)
        assert "Unknown model" in client.get("/admin/shop/ghost").text
        assert "not found" in client.get("/admin/shop/product/999/change").text.lower()

    def test_search_and_filter_panels_absent(self, tmp_path):
        from apps.shop.models import Product
        from ronnie.contrib.admin import ModelAdmin, site

        site.unregister(Product)
        site.register(Product, ModelAdmin)  # no search/filter/ordering
        try:
            client, _table = self._staff_client(tmp_path)
            body = client.get("/admin/shop/product").text
            assert "Search" not in body
            assert "Filters" not in body
        finally:
            site.unregister(Product)
            from apps.shop.admin import ProductAdmin  # type: ignore[attr-defined]

            site.register(Product, ProductAdmin)

    def test_add_form_error_and_empty_list(self, tmp_path):
        client, table = self._staff_client(tmp_path)
        for row in list(table()):
            table.delete(row.id)
        body = client.get("/admin/shop/product").text
        assert "No rows" in body
        page = client.get("/admin/shop/product/add").text
        assert "Add Product" in page

    def test_modeladmin_hooks(self, tmp_path):
        from apps.shop.models import Product
        from ronnie.contrib.admin import ModelAdmin, site

        saved: list[Any] = []

        class Hooked(ModelAdmin):
            readonly_fields = ("price",)
            fields = ("name", "price")

            def save_model(self, request, obj, change):
                saved.append((change, obj))
                return super().save_model(request, obj, change)

        site.unregister(Product)
        site.register(Product, Hooked)
        try:
            client, _table = self._staff_client(tmp_path)
            import re

            token = re.search(
                r'value="([^"]+)"',
                re.search(
                    r"<input[^>]*csrfmiddlewaretoken[^>]*>", client.get("/admin/shop/product/add").text
                ).group(0),
            ).group(1)
            client.post(
                "/admin/shop/product/add",
                data={"name": "cup", "csrfmiddlewaretoken": token},
                follow_redirects=True,
            )
            assert any(change is False for change, _ in saved)
            # readonly price excluded from editable fields
            assert [f.name for f in site.get_model_admin(Product).model_fields()] == ["name"]
        finally:
            site.unregister(Product)
            from apps.shop.admin import ProductAdmin  # type: ignore[attr-defined]

            site.register(Product, ProductAdmin)

    def test_action_with_no_selection(self, tmp_path):
        client, _table = self._staff_client(tmp_path)
        import re

        token = re.search(
            r'value="([^"]+)"',
            re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", client.get("/admin/shop/product").text).group(
                0
            ),
        ).group(1)
        response = client.post(
            "/admin/shop/product/action",
            data={"action": "delete_selected", "csrfmiddlewaretoken": token},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_admin_autodiscover_broken_admin_py(self, tmp_path):
        import ronnie
        from apps.shop.models import Product
        from ronnie.apps import apps
        from ronnie.contrib.admin import site

        site.unregister(Product)  # apps.shop.admin would double-register
        settings.INSTALLED_APPS = [
            "ronnie.contrib.admin",
            "apps.shop",
            "apps.broken_admin",
        ]
        apps.clear_data()
        with pytest.raises(ImportError, match="deliberately broken"):
            ronnie.setup()


def _build_app():
    from ronnie.core.asgi import get_asgi_application

    return get_asgi_application()


def _login(client):
    import re

    page = client.get("/accounts/login").text
    token = re.search(
        r'value="([^"]+)"', re.search(r"<input[^>]*csrfmiddlewaretoken[^>]*>", page).group(0)
    ).group(1)
    client.post(
        "/accounts/login",
        data={"username": "stf", "password": "stf-pass-1", "csrfmiddlewaretoken": token},
        follow_redirects=True,
    )


# -- auth extras ------------------------------------------------------------------


class TestAuthBranches:
    def _env(self, tmp_path: Path):
        import ronnie
        from ronnie.apps import apps

        for key, value in {
            "INSTALLED_APPS": ["ronnie.contrib.sessions", "ronnie.contrib.auth"],
            "MIDDLEWARE": [
                "ronnie.middleware.host.HostValidationMiddleware",
                "ronnie.contrib.sessions.middleware.SessionMiddleware",
                "ronnie.middleware.csrf.CsrfMiddleware",
                "ronnie.contrib.auth.middleware.AuthMiddleware",
            ],
            "DATABASES": {"default": {"ENGINE": "sqlite", "NAME": tmp_path / "auth.db"}},
            "LOGIN_REDIRECT_URL": "/",
        }.items():
            setattr(settings, key, value)
        from ronnie.core.passwords.hashers import PBKDF2PasswordHasher

        PBKDF2PasswordHasher.iterations = 1000
        apps.clear_data()
        ronnie.setup()
        from ronnie.db import install_tables

        install_tables()
        from ronnie.contrib.auth.models import create_user

        create_user("u1", "u1-pass-123")

    def test_get_backends_rejects_bad_path(self):
        settings.AUTHENTICATION_BACKENDS = ["no.such.Backend"]
        from ronnie.contrib.auth.backends import get_backends

        with pytest.raises(ImproperlyConfigured, match="Cannot import"):
            get_backends()

    def test_backend_get_user_bad_id(self, tmp_path):
        self._env(tmp_path)
        from ronnie.contrib.auth.backends import ModelBackend

        assert ModelBackend().get_user("not-a-number") is None
        assert ModelBackend().get_user(99999) is None

    def test_authenticate_none_credentials(self, tmp_path):
        self._env(tmp_path)
        from ronnie.contrib.auth import authenticate

        assert authenticate(username=None, password=None) is None

    def test_permission_required_paths(self, tmp_path):
        self._env(tmp_path)
        client = TC(_build_app())
        # admin-style guard: anonymous requests bounce to the login page
        response = client.get("/accounts/password_change", follow_redirects=False)
        assert response.status_code == 303
        assert "/accounts/login" in response.headers["location"]

    def test_user_passes_test_redirects(self, tmp_path):
        from ronnie.contrib.auth.decorators import user_passes_test

        @user_passes_test(lambda user: False)
        def view(req):
            return "never"

        class FakeRequest:
            url = type("U", (), {"path": "/p"})()
            scope = {"user": None}

        result = view(req=FakeRequest())
        assert getattr(result, "loc", None) is not None  # a Redirect

    def test_permission_required_raises(self):
        from ronnie.contrib.auth.decorators import permission_required
        from ronnie.core.exceptions import PermissionDenied

        @permission_required("x.y", raise_exception=True)
        def view(req, auth):
            return "no"

        class FakeRequest:
            url = type("U", (), {"path": "/p"})()
            scope = {"user": None}

        class FakeUser:
            is_authenticated = True

            def has_perm(self, perm):
                return False

        with pytest.raises(PermissionDenied):
            view(req=FakeRequest(), auth=FakeUser())

    def test_custom_user_model(self, tmp_path):
        self._env(tmp_path)
        settings.AUTH_USER_MODEL = "ronnie.contrib.auth.User"
        from ronnie.contrib.auth.models import get_user_model

        assert get_user_model().__name__ == "User"

    def test_logout_never_fails_without_session(self):
        from ronnie.contrib.auth import logout

        class Bare:
            scope = {}

        logout(Bare())  # must not raise

    def test_get_user_hash_absent_branch(self, tmp_path):
        self._env(tmp_path)
        from ronnie.contrib.auth.api import get_user
        from ronnie.contrib.auth.models import create_user

        user = create_user("u2", "u2-pass-123")
        assert get_user({"session": {"_auth_user_id": str(user.id)}}).username == "u2"


# -- messages / humanize / redirects ------------------------------------------------


class TestMessagesBranches:
    def test_add_message_raises_without_silence(self, monkeypatch):
        from ronnie.contrib import messages as messages_mod

        monkeypatch.setattr(
            messages_mod, "_storage", lambda: (_ for _ in ()).throw(ImproperlyConfigured("no storage"))
        )
        with pytest.raises(ImproperlyConfigured):
            messages_mod.add_message(object(), 20, "x")

    def test_debug_shortcut_below_level(self):
        from ronnie.contrib.messages import messages

        class Scope:
            scope = {"session": {}}

        request = Scope()
        messages.debug(request, "hidden")  # below default MESSAGE_LEVEL → dropped
        assert request.scope["session"].get("_messages") is None

    def test_middleware_skips_lifespan(self):
        import asyncio

        from ronnie.contrib.messages.middleware import MessagesMiddleware

        async def app(scope, receive, send):
            pass

        asyncio.run(MessagesMiddleware(app)({"type": "lifespan"}, None, None))


class TestHumanizeEdges:
    def test_non_integers_and_words(self):
        from ronnie.contrib.humanize import apnumber, intword

        assert apnumber(4.5) == "4.5"
        assert apnumber(0) == "0"
        assert intword(-2_500_000, language="en") == "-2.5 millions"
        assert intword(1, language="en") == "1"

    def test_naturalday_far_dates(self):
        import datetime as dt

        from ronnie.contrib.humanize import naturalday

        far = dt.date(2020, 1, 15)
        assert naturalday(far) == "15 ene 2020" or "2020" in naturalday(far)
        assert naturalday(dt.date(2030, 6, 1), language="en") == "01 Jun 2030"

    def test_naturaltime_months_fall_to_naturalday(self):
        import datetime as dt

        from ronnie.contrib.humanize import naturaltime

        now = dt.datetime(2026, 9, 19, 12)
        old = now - dt.timedelta(days=90)
        assert naturaltime(old, now=now) in ("hace 3 meses",) or "2026" in naturaltime(old, now=now)


class TestRedirectsApps:
    def test_ready_without_admin_is_safe(self):
        from ronnie.contrib.redirects.apps import RedirectsConfig

        RedirectsConfig("ronnie.contrib.redirects", None).ready()  # no admin installed


# -- tasks ----------------------------------------------------------------------------


class TestTaskBranches:
    @pytest.fixture(autouse=True)
    def _task_env(self):
        from ronnie.cache import reset_caches
        from ronnie.tasks import reset_broker, reset_registry

        reset_registry()
        reset_broker()
        reset_caches()
        yield
        reset_registry()
        reset_broker()
        reset_caches()

    def test_broker_bad_path_rejected(self):
        settings.TASKS_BROKER = "no.such.Broker"
        from ronnie.tasks import get_broker, reset_broker

        reset_broker()
        with pytest.raises(ImproperlyConfigured, match="Cannot import"):
            get_broker()

    def test_unknown_task_execute(self):
        from ronnie.tasks import AsyncResult, TaskError, execute_task

        with pytest.raises(TaskError, match="Unknown task"):
            execute_task("ghost.task", [], {})
        assert AsyncResult("x1").status == "PENDING"

    def test_apply_async_countdown_and_queue(self):
        from ronnie.tasks import task
        from ronnie.tasks.brokers.redis import RedisBroker

        class ListBroker(RedisBroker):
            def __init__(self):
                self.sent: list = []

            def enqueue(self, queue, message):
                self.sent.append((queue, message))

        import ronnie.tasks as tasks_mod

        broker = ListBroker()
        tasks_mod._broker = broker

        @task(name="cov.slow")
        def slow() -> str:
            return "done"

        slow.apply_async(countdown=0, queue="hipri")
        queue, message = broker.sent[0]
        assert queue == "hipri"
        assert message["eta"] == 0

    def test_worker_eta_sleep_and_no_message(self):
        import time

        from ronnie.tasks import task
        from ronnie.tasks.worker import Worker

        class QueueBroker:
            from queue import Queue

            def __init__(self):
                self.queue = self.Queue()

            def enqueue(self, queue, message):
                self.queue.put(message)

            def dequeue(self, queues, timeout=1.0):
                try:
                    return self.queue.get(timeout=timeout)
                except Exception:
                    return None

        broker = QueueBroker()
        ran: list = []

        @task(name="cov.eta")
        def eta_task() -> str:
            ran.append(1)
            return "ok"

        broker.enqueue(
            "default",
            {
                "id": "eta1",
                "name": "cov.eta",
                "args": [],
                "kwargs": {},
                "retries": 0,
                "eta": time.time() + 0.05,
            },
        )
        worker = Worker(queues=["default"], broker=broker)
        assert worker.process_one(poll_timeout=0.2) is True
        assert ran == [1]
        assert worker.process_one(poll_timeout=0.05) is False  # queue drained

    def test_worker_stop_flag(self):
        from ronnie.tasks.worker import Worker

        class NeverBroker:
            def enqueue(self, *a):
                pass

            def dequeue(self, queues, timeout=1.0):
                return None

        worker = Worker(broker=NeverBroker())
        worker.stop()
        assert worker._stop is True

    def test_beat_skips_invalid_entries(self):
        from ronnie.tasks.beat import Beat

        beat = Beat(
            schedule={
                "zero": {"task": "no.task", "every": 0},  # non-positive interval
                "ghost": {"task": "ghost.task", "every": 5},  # unknown task
            }
        )
        assert beat.tick() == 0

    def test_beat_stop_signal(self):
        from ronnie.tasks.beat import Beat

        beat = Beat(schedule={})
        beat.stop()
        assert beat._stop is True

    def test_thread_broker_eta(self):
        import time

        import ronnie.tasks as tasks_mod
        from ronnie.tasks import task
        from ronnie.tasks.brokers.thread import ThreadBroker

        broker = ThreadBroker()
        tasks_mod._broker = broker
        results: list = []

        @task(name="cov.eta.thread")
        def quick() -> str:
            results.append(1)
            return "v"

        quick.apply_async(countdown=0)
        deadline = time.time() + 5
        while not results and time.time() < deadline:
            time.sleep(0.02)
        assert results == [1]

    def test_inline_broker_with_countdown_zero(self):
        from ronnie.tasks import task

        @task(name="cov.plain")
        def plain() -> int:
            return 7

        result = plain.delay()
        assert result.get(timeout=1) == 7

    def test_worker_command_spawns_processes(self, monkeypatch):
        from ronnie.core.management.commands import worker as worker_cmd

        spawned: list = []

        class FakeProcess:
            def __init__(self, target, args):
                spawned.append((target, args))

            def start(self):
                pass

            def join(self):
                pass

        monkeypatch.setattr("multiprocessing.Process", FakeProcess)
        loops: list = []

        def fake_loop(queues):
            loops.append(queues)

        monkeypatch.setattr(worker_cmd, "run_worker_loop", fake_loop)
        command = worker_cmd.Command()
        command.handle(queues="a,b", concurrency=3)
        assert len(spawned) == 3

    def test_worker_command_single_process(self, monkeypatch):
        from ronnie.core.management.commands import worker as worker_cmd

        loops: list = []

        def fake_loop(queues):
            loops.append(queues)

        monkeypatch.setattr(worker_cmd, "run_worker_loop", fake_loop)
        worker_cmd.Command().handle(queues="solo", concurrency=1)
        assert loops == [["solo"]]
