"""Tasks framework: ``@task`` decorator, pluggable brokers, results, workers.

::

    from ronnie.tasks import task

    @task(max_retries=3, retry_backoff=True)
    def rebuild_index(post_id: int): ...

    rebuild_index.delay(post_id=42)      # enqueue (JSON-serializable args)
    rebuild_index.call(post_id=42)       # run synchronously, now

Brokers (``TASKS_BROKER``): inline (default; runs synchronously — perfect for
tests and DEBUG), thread (background pool), redis (extra ``ronnie[redis]``).
Results live in the cache framework by default (``TASKS_RESULT_BACKEND``).
"""

from __future__ import annotations

import functools
import json
import time
import traceback
import uuid
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from ..core.signals import Signal

__all__ = [
    "FAILED",
    "PENDING",
    "RETRY",
    "STARTED",
    "SUCCESS",
    "Task",
    "get_broker",
    "registry",
    "reset_broker",
    "reset_registry",
    "task",
    "task_failure",
    "task_postrun",
    "task_prerun",
]

PENDING, STARTED, SUCCESS, FAILED, RETRY = "PENDING", "STARTED", "SUCCESS", "FAILED", "RETRY"

task_prerun = Signal()
task_postrun = Signal()
task_failure = Signal()

registry: dict[str, Task] = {}


class Task:
    """A registered callable plus execution options."""

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        max_retries: int | None = None,
        retry_backoff: bool = True,
    ) -> None:
        self.func = func
        self.name = name or f"{func.__module__}.{func.__qualname__}"
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        functools.update_wrapper(self, func)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)

    # -- dispatch -------------------------------------------------------------------

    def delay(self, *args: Any, **kwargs: Any) -> AsyncResult:
        return self.apply_async(args=args, kwargs=kwargs)

    def apply_async(
        self,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        *,
        countdown: int = 0,
        queue: str | None = None,
    ) -> AsyncResult:
        from ..conf import settings

        message = {
            "id": uuid.uuid4().hex,
            "name": self.name,
            "args": list(args),
            "kwargs": dict(kwargs or {}),
            "retries": 0,
            "eta": time.time() + countdown if countdown else 0,
        }
        queue_name = queue or str(getattr(settings._wrapped, "TASKS_DEFAULT_QUEUE", None) or "default")
        get_broker().enqueue(queue_name, message)
        return AsyncResult(str(message["id"]))

    def call(self, *args: Any, **kwargs: Any) -> Any:
        """Execute synchronously (bypassing the broker), recording the result."""
        return execute_task(self.name, list(args), dict(kwargs), retries=0)


def task(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    max_retries: int | None = None,
    retry_backoff: bool = True,
) -> Any:
    """Decorator registering a function as a Ronnie task."""

    def register(fn: Callable[..., Any]) -> Task:
        instance = Task(fn, name=name, max_retries=max_retries, retry_backoff=retry_backoff)
        registry[instance.name] = instance
        return instance

    return register(func) if func is not None else register


def reset_registry() -> None:
    """Test helper: forget all registered tasks."""
    registry.clear()


# -- brokers -------------------------------------------------------------------------


@runtime_checkable
class Broker(Protocol):
    def enqueue(self, queue: str, message: dict[str, Any]) -> None: ...

    def dequeue(self, queues: list[str], timeout: float = 1.0) -> dict[str, Any] | None: ...


_broker: Broker | None = None


def get_broker() -> Broker:
    global _broker
    if _broker is None:
        import importlib

        from ..conf import settings
        from ..core.exceptions import ImproperlyConfigured

        path = str(
            getattr(settings._wrapped, "TASKS_BROKER", None) or "ronnie.tasks.brokers.inline.InlineBroker"
        )
        module_path, _, attr = path.rpartition(".")
        try:
            cls = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError) as exc:
            raise ImproperlyConfigured(f"Cannot import task broker {path!r}: {exc}") from exc
        _broker = cls() if isinstance(cls, type) else cls
    return _broker


def reset_broker() -> None:
    """Test helper: rebuild the broker from settings on next use."""
    global _broker
    _broker = None


# -- results ---------------------------------------------------------------------------


def _results_cache() -> Any:
    from ..cache import caches
    from ..conf import settings

    backend = str(getattr(settings._wrapped, "TASKS_RESULT_BACKEND", None) or "cache:default")
    _, _, alias = backend.partition(":")
    return caches[alias or "default"]


def store_result(task_id: str, state: str, value: Any = None, tb: str = "") -> None:
    _results_cache().set(
        f"ronnie.task.result:{task_id}",
        {"state": state, "value": value, "traceback": tb, "ts": time.time()},
        timeout=3600,
    )


class AsyncResult:
    """Handle for a submitted task (poll or ``get`` with timeout)."""

    def __init__(self, task_id: str) -> None:
        self.id = task_id

    def _read(self) -> dict[str, Any] | None:
        record = _results_cache().get(f"ronnie.task.result:{self.id}")
        return record if isinstance(record, dict) else None

    @property
    def status(self) -> str:
        record = self._read()
        return record["state"] if record else PENDING

    @property
    def traceback(self) -> str:
        record = self._read() or {}
        return str(record.get("traceback", ""))

    def get(self, timeout: float = 10.0) -> Any:
        deadline = time.time() + timeout
        while time.time() < deadline:
            record = self._read()
            if record:
                if record["state"] == SUCCESS:
                    return record.get("value")
                if record["state"] == FAILED:
                    raise TaskError(record.get("traceback", ""))
            time.sleep(0.05)
        raise TimeoutError(f"Result for task {self.id} not ready in {timeout}s.")


class TaskError(Exception):
    pass


# -- execution -----------------------------------------------------------------------------


def execute_task(
    name: str, args: list[Any], kwargs: dict[str, Any], retries: int = 0, task_id: str | None = None
) -> Any:
    """Run a registered task: signals, result storage, retry policy."""
    from ..conf import settings

    task_id = task_id or uuid.uuid4().hex
    instance = registry.get(name)
    if instance is None:
        store_result(task_id, FAILED, tb=f"Unknown task {name!r}.")
        raise TaskError(f"Unknown task {name!r}.")

    task_prerun.send(sender=instance, task_id=task_id, retries=retries)
    store_result(task_id, STARTED)
    try:
        result = instance.func(*args, **kwargs)
    except Exception:
        tb = traceback.format_exc()
        task_failure.send(sender=instance, task_id=task_id, retries=retries, traceback=tb)
        max_retries = instance.max_retries
        if max_retries is None:
            max_retries = int(getattr(settings._wrapped, "TASKS_MAX_RETRIES", None) or 0)
        if retries < max_retries:
            store_result(task_id, RETRY, tb=tb)
            from . import worker as worker_mod

            worker_mod.schedule_retry(
                name, args, kwargs, retries + 1, backoff=instance.retry_backoff, task_id=task_id
            )
        else:
            store_result(task_id, FAILED, tb=tb)
        return None
    store_result(task_id, SUCCESS, value=result)
    task_postrun.send(sender=instance, task_id=task_id, result=result)
    return result


def encode_message(message: dict[str, Any]) -> str:
    return json.dumps(message)


def decode_message(raw: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(raw)
    return loaded
