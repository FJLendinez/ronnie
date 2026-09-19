"""InlineBroker: run tasks synchronously on enqueue (tests, DEBUG)."""

from __future__ import annotations

from typing import Any

from .. import execute_task


class InlineBroker:
    def enqueue(self, queue: str, message: dict[str, Any]) -> None:
        if message.get("eta") and message["eta"] > 0:
            import time

            time.sleep(max(0, message["eta"] - time.time()))
        execute_task(
            message["name"],
            message["args"],
            message["kwargs"],
            retries=message.get("retries", 0),
            task_id=message["id"],
        )

    def dequeue(self, queues: list[str], timeout: float = 1.0) -> dict[str, Any] | None:
        return None  # nothing is ever queued
