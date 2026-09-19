"""Tests for the tasks framework (Fase 13)."""

from __future__ import annotations

from typing import Any

import pytest

from ronnie.cache import reset_caches
from ronnie.conf import settings
from ronnie.tasks import (
    FAILED,
    PENDING,
    RETRY,
    SUCCESS,
    AsyncResult,
    registry,
    reset_broker,
    reset_registry,
    task,
    task_failure,
    task_postrun,
    task_prerun,
)
from ronnie.tasks.brokers.redis import RedisBroker
from ronnie.tasks.worker import Worker


class FakeRedisBroker(RedisBroker):
    def _create_client(self) -> Any:
        import fakeredis

        return fakeredis.FakeRedis()


class QueueBroker:
    """Minimal in-memory queue broker for worker-loop tests."""

    def __init__(self) -> None:
        from queue import Queue

        self.queue: Queue = Queue()

    def enqueue(self, queue: str, message: dict) -> None:
        self.queue.put(message)

    def dequeue(self, queues: list[str], timeout: float = 1.0) -> dict | None:
        try:
            return self.queue.get(timeout=timeout)
        except Exception:
            return None


@pytest.fixture(autouse=True)
def _task_env():
    settings.configure(SECRET_KEY="k", TASKS_MAX_RETRIES=2, TASKS_RETRY_BACKOFF=False)
    reset_registry()
    reset_broker()
    reset_caches()
    yield
    reset_registry()
    reset_broker()
    reset_caches()


class TestRegistryAndInline:
    def test_task_registration_and_direct_call(self):
        @task
        def add(a: int, b: int = 1) -> int:
            return a + b

        assert add.name in registry
        assert add.call(2, b=3) == 5

    def test_delay_executes_inline(self):
        calls: list[str] = []

        @task
        def note(what: str) -> str:
            calls.append(what)
            return what.upper()

        result = note.delay("hi")
        assert calls == ["hi"]
        assert result.get(timeout=1) == "HI"
        assert result.status == SUCCESS

    def test_result_lifecycle_failure(self):
        @task(max_retries=0)
        def boom() -> None:
            raise RuntimeError("kaboom")

        result = boom.delay()
        assert result.status == FAILED
        assert "kaboom" in result.traceback
        with pytest.raises(Exception, match="kaboom"):
            result.get(timeout=1)

    def test_pending_result_get_times_out(self):
        result = AsyncResult("no-such-id")
        assert result.status == PENDING
        with pytest.raises(TimeoutError):
            result.get(timeout=0.2)

    def test_signals_fire(self):
        events: list[str] = []
        task_prerun.connect(lambda sender, **kw: events.append("pre"), weak=False)
        task_postrun.connect(lambda sender, **kw: events.append("post"), weak=False)
        task_failure.connect(lambda sender, **kw: events.append("fail"), weak=False)

        @task(max_retries=0)
        def ok() -> int:
            return 1

        @task(max_retries=0)
        def bad() -> None:
            raise ValueError("x")

        ok.delay()
        bad.delay()
        assert "pre" in events and "post" in events and "fail" in events


class TestRetries:
    def test_retry_then_success(self, monkeypatch):
        attempts = {"n": 0}

        @task(max_retries=2, retry_backoff=False)
        def flaky() -> str:
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ValueError("not yet")
            return "ok"

        result = flaky.delay()
        assert result.status == RETRY  # failed first attempt, retry scheduled

        from ronnie.tasks.worker import Worker

        worker = Worker(broker=QueueBroker())
        worked = worker.process_one(poll_timeout=0.1)  # runs due retry
        assert worked
        assert attempts["n"] == 2
        final = AsyncResult(result.id)
        assert final.status == SUCCESS
        assert final.get(timeout=1) == "ok"

    def test_retries_exhausted(self):
        @task(max_retries=1, retry_backoff=False)
        def always_bad() -> None:
            raise ValueError("nope")

        result = always_bad.delay()  # attempt 1 → RETRY
        assert result.status == RETRY
        worker = Worker(broker=QueueBroker())
        worker.process_one(poll_timeout=0.1)  # attempt 2 → FAILED
        assert AsyncResult(result.id).status == FAILED


class TestBrokers:
    def test_thread_broker_runs_in_background(self):
        import ronnie.tasks as tasks_mod
        from ronnie.tasks.brokers.thread import ThreadBroker

        tasks_mod._broker = ThreadBroker()

        @task
        def compute() -> int:
            return 21 * 2

        result = compute.delay()
        assert result.get(timeout=5) == 42

    def test_redis_broker_roundtrip(self):
        broker = FakeRedisBroker()

        @task
        def noop() -> int:
            return 0

        message = {
            "id": "abc",
            "name": noop.name,
            "args": [],
            "kwargs": {},
            "retries": 0,
            "eta": 0,
        }
        broker.enqueue("default", message)
        got = broker.dequeue(["default"], timeout=1)
        assert got == message

    def test_worker_consumes_broker_queue(self):
        broker = QueueBroker()

        @task
        def greet(name: str) -> str:
            return f"hola {name}"

        message = {
            "id": "job1",
            "name": greet.name,
            "args": ["mundo"],
            "kwargs": {},
            "retries": 0,
            "eta": 0,
        }
        broker.enqueue("default", message)
        worker = Worker(queues=["default"], broker=broker)
        assert worker.process_one(poll_timeout=0.5) is True
        assert AsyncResult("job1").get(timeout=1) == "hola mundo"


class TestBeat:
    def test_interval_dispatch(self):
        fired: list[str] = []

        @task(name="beat.ping")
        def ping() -> None:
            fired.append("ping")

        beat_cls = __import__("ronnie.tasks.beat", fromlist=["Beat"]).Beat
        beat = beat_cls(schedule={"p": {"task": "beat.ping", "every": 10}})
        import time as time_mod

        now = time_mod.time()
        assert beat.tick(now=now) == 1  # first fire
        assert beat.tick(now=now + 5) == 0  # not due yet
        assert beat.tick(now=now + 11) == 1  # next interval
        assert fired == ["ping", "ping"]


class TestDiscovery:
    def test_apps_tasks_module_imported_on_populate(self):
        import ronnie
        from ronnie.apps import apps

        apps.clear_data()
        reset_registry()

        # apps.blog has no tasks.py; shop neither — discovery must not fail.
        settings.INSTALLED_APPS = ["apps.shop", "apps.pages"]
        ronnie.setup()
        assert apps.ready

        # Register a tasks module dynamically to prove the hook works.
        import sys
        import types

        module = types.ModuleType("apps.shop.tasks")

        @task(name="shop.background")
        def background() -> str:
            return "done"

        module.background = background
        sys.modules["apps.shop.tasks"] = module
        try:
            apps.clear_data()
            ronnie.setup()
            assert "shop.background" in registry
        finally:
            del sys.modules["apps.shop.tasks"]
            reset_registry()
