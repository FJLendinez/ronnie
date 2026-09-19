"""ThreadBroker: background execution via a small thread pool (dev)."""

from __future__ import annotations

import queue as queue_mod
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .. import execute_task


class ThreadBroker:
    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._queue: queue_mod.Queue[dict[str, Any] | None] = queue_mod.Queue()

    def _run(self, message: dict[str, Any]) -> None:
        import time

        if message.get("eta") and message["eta"] > time.time():
            time.sleep(message["eta"] - time.time())
        execute_task(
            message["name"],
            message["args"],
            message["kwargs"],
            retries=message.get("retries", 0),
            task_id=message["id"],
        )

    def enqueue(self, queue: str, message: dict[str, Any]) -> None:
        self._pool.submit(self._run, message)

    def dequeue(self, queues: list[str], timeout: float = 1.0) -> dict[str, Any] | None:
        try:
            return self._queue.get(timeout=timeout) or None
        except queue_mod.Empty:
            return None
