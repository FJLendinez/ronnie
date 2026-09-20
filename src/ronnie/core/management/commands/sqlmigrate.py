"""Print the SQL a migration would run."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.core.management import BaseCommand
from ronnie.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Print the SQL for a migration (applied or pending)."
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("app_label")
        parser.add_argument("migration_name", help="Migration name or its numeric prefix (e.g. 0002).")

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.db import get_database

        executor = MigrationExecutor(get_database())
        node = executor._node(options["app_label"], options["migration_name"])
        statements = executor.apply(node, dry_run=True, log=lambda _m: None)
        if not statements:
            self.stdout.write(f"-- {node.app}.{node.name}: no SQL (data-only migration)")
            return
        self.stdout.write(f"-- {node.app}.{node.name}")
        for statement in statements:
            self.stdout.write(statement + ";")
