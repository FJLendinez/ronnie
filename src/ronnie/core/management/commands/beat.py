"""Run the periodic-task scheduler (``ronnie beat``)."""

from __future__ import annotations

from typing import Any

from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Run the Ronnie beat scheduler (TASKS_SCHEDULE intervals)."
    requires_system_checks = ()

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.tasks.beat import Beat

        self.stdout.write(self.style.SUCCESS("Beat scheduler started."))
        Beat().run()  # pragma: no cover - blocking loop
