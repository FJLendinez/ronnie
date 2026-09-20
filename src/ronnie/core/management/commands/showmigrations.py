"""List migrations and their applied state ([X] applied, [ ] pending)."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.core.management import BaseCommand
from ronnie.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Show the status of every migration."
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("app_label", nargs="?", help="Limit to one app.")

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.db import get_database

        executor = MigrationExecutor(get_database())
        applied = executor.recorder.applied()
        label = options.get("app_label")
        for app, nodes in executor.loader.by_app().items():
            if label and app != label:
                continue
            self.stdout.write(app)
            done = set(applied.get(app, []))
            for node in nodes:
                marker = "[X]" if node.name in done else "[ ]"
                if node.name in done:
                    self.stdout.write(self.style.SUCCESS(f"  {marker} {node.name}"))
                else:
                    self.stdout.write(f"  {marker} {node.name}")
        if not executor.loader.nodes:
            self.stdout.write("No migrations found. Run `ronnie makemigrations`.")
