"""Run a task worker (``ronnie worker``)."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Run a Ronnie task worker (consumes queues; graceful on SIGTERM)."
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--queues", "-q", default="default", help="Comma-separated queue names.")
        parser.add_argument(
            "--concurrency", "-c", type=int, default=1, help="Worker processes (1 = in-process loop)."
        )

    def handle(self, *args: Any, **options: Any) -> None:

        queues = [q.strip() for q in options["queues"].split(",") if q.strip()]
        if options["concurrency"] > 1:
            import multiprocessing as mp

            self.stdout.write(self.style.SUCCESS(f"Starting {options['concurrency']} workers on {queues}…"))
            procs = [
                mp.Process(target=run_worker_loop, args=(queues,)) for _ in range(options["concurrency"])
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join()
        else:
            self.stdout.write(self.style.SUCCESS(f"Worker listening on {queues}…"))
            run_worker_loop(queues)


def run_worker_loop(queues: list[str]) -> None:  # pragma: no cover - blocking loop
    from ronnie.tasks.worker import Worker

    Worker(queues=queues).run()
