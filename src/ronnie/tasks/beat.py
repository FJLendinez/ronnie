"""Beat scheduler: run TASKS_SCHEDULE entries at fixed intervals.

Schedule format (``TASKS_SCHEDULE``)::

    TASKS_SCHEDULE = {
        "cleanup-hourly": {"task": "myapp.tasks.cleanup", "every": 3600},
    }

Cron expressions are on the roadmap; use ``every`` seconds for now.
"""

from __future__ import annotations

import time
from typing import Any

__all__ = ["Beat"]


class Beat:
    def __init__(self, schedule: dict[str, dict[str, Any]] | None = None) -> None:
        from ..conf import settings

        self.schedule = (
            schedule
            if schedule is not None
            else dict(getattr(settings._wrapped, "TASKS_SCHEDULE", None) or {})
        )
        self._next_run: dict[str, float] = {}
        self._stop = False

    def stop(self, *_args: Any) -> None:
        self._stop = True

    def tick(self, now: float | None = None) -> int:
        """Fire every due entry once; returns the number of tasks dispatched."""
        from . import registry

        now = now if now is not None else time.time()
        dispatched = 0
        for name, entry in self.schedule.items():
            interval = float(entry.get("every", 0))
            if interval <= 0:
                continue
            if self._next_run.get(name, 0) <= now:
                self._next_run[name] = now + interval  # drift-corrected
                task_name = str(entry.get("task", ""))
                instance = registry.get(task_name)
                if instance is None:
                    continue
                instance.delay()
                dispatched += 1
        return dispatched

    def run(self) -> None:  # pragma: no cover - long loop
        import signal

        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        while not self._stop:
            self.tick()
            time.sleep(0.1)
