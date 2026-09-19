"""Worker loop: consume queues, run tasks, honour retries and shutdown."""

from __future__ import annotations

import signal
import time
from typing import Any

from . import execute_task, get_broker

__all__ = ["Worker", "schedule_retry"]

_retry_queue: list[tuple[str, list[Any], dict[str, Any], int, float, str]] = []


def schedule_retry(
    name: str,
    args: list[Any],
    kwargs: dict[str, Any],
    attempt: int,
    *,
    backoff: bool = True,
    task_id: str = "",
) -> None:
    """Re-queue a failed task, keeping its result id (polled by AsyncResult)."""
    delay = min(2**attempt, 60) if backoff else 0
    _retry_queue.append((name, args, kwargs, attempt, time.time() + delay, task_id))


class Worker:
    def __init__(self, queues: list[str] | None = None, broker: Any = None) -> None:
        from ..conf import settings

        self.queues = queues or [str(getattr(settings._wrapped, "TASKS_DEFAULT_QUEUE", None) or "default")]
        self.broker = broker or get_broker()
        self._stop = False

    def stop(self, *_args: Any) -> None:
        self._stop = True

    # -- loop ------------------------------------------------------------------------

    def run(self, poll_timeout: float = 1.0) -> None:  # pragma: no cover - long loop
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        while not self._stop:
            self.process_one(poll_timeout)

    def process_one(self, poll_timeout: float = 1.0) -> bool:
        """Handle pending retries, then one broker message. True if work was done."""
        worked = self._run_due_retries()
        message = self.broker.dequeue(self.queues, timeout=poll_timeout)
        if message is None:
            return worked
        self._execute_message(message)
        return True

    def _execute_message(self, message: dict[str, Any]) -> None:
        if message.get("eta") and message["eta"] > time.time():
            time.sleep(max(0, message["eta"] - time.time()))
        execute_task(
            message["name"],
            message.get("args", []),
            message.get("kwargs", {}),
            retries=message.get("retries", 0),
            task_id=message["id"],
        )

    def _run_due_retries(self) -> bool:
        from . import registry

        worked = False
        still_pending: list[tuple[str, list[Any], dict[str, Any], int, float, str]] = []
        for name, args, kwargs, attempt, due_at, task_id in _retry_queue:
            if time.time() >= due_at and name in registry:
                execute_task(name, args, kwargs, retries=attempt, task_id=task_id or None)
                worked = True
            else:
                still_pending.append((name, args, kwargs, attempt, due_at, task_id))
        _retry_queue[:] = still_pending
        return worked
