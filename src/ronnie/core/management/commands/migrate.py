"""Apply pending migrations (recorded in the ronnie_migration table)."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.core.management import BaseCommand
from ronnie.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Apply (or roll back) migrations recorded in ronnie_migration."
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("app_label", nargs="?", help="Limit to one app.")
        parser.add_argument("migration_name", nargs="?", help="Target migration ('zero' rolls back all).")
        parser.add_argument("--fake", action="store_true", help="Record migrations without running them.")
        parser.add_argument(
            "--fake-initial",
            action="store_true",
            help="Fake initial CreateTables whose tables already exist.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Print SQL without executing or recording."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.db import get_database

        db = get_database()
        executor = MigrationExecutor(db)
        app_label: str | None = options.get("app_label")
        target: str | None = options.get("migration_name")

        if app_label and (not target or target == "zero"):
            from ronnie.apps import apps

            apps.get_app_config(app_label)  # validate label early
        elif app_label and target:
            executor._node(app_label, target)  # validate label + target

        if target and target != "zero" and app_label:
            return self._migrate_to(executor, app_label, target, options)

        if target == "zero":
            return self._rollback_all(executor, app_label, options)

        pending = [n for n in executor.pending() if not app_label or n.app == app_label]
        if not pending:
            if not executor.loader.nodes:
                self.stdout.write("No migrations found. Run `ronnie makemigrations` to create them.")
                return
            self.stdout.write(self.style.SUCCESS("No migrations to apply."))
            return

        self.stdout.write("Operations to perform:")
        self.stdout.write(f"  Apply all migrations: {', '.join(sorted({n.app for n in pending}))}")
        for node in pending:
            sql = executor.apply(
                node,
                fake=options.get("fake", False),
                fake_initial=options.get("fake_initial", False),
                dry_run=options.get("dry_run", False),
                log=self._log(options),
            )
            if options.get("dry_run") or options.get("verbosity", 1) >= 2:
                for statement in sql:
                    self.stdout.write(f"    {statement}")

    def _log(self, options: Any) -> Any:
        quiet = options.get("verbosity", 1) == 0
        return (lambda _msg: None) if quiet else self.stdout.write

    def _migrate_to(self, executor: MigrationExecutor, app: str, target: str, options: Any) -> None:
        node = executor._node(app, target)
        applied = executor.recorder.applied().get(app, [])
        if node.name in applied:
            self._rollback_to(executor, app, node.name, options)
            return
        pending = [n for n in executor.pending() if n.app == app]
        for candidate in pending:
            executor.apply(
                candidate,
                fake=options.get("fake", False),
                fake_initial=options.get("fake_initial", False),
                dry_run=options.get("dry_run", False),
                log=self._log(options),
            )
            if candidate.name == node.name:
                break

    def _rollback_to(self, executor: MigrationExecutor, app: str, target: str, options: Any) -> None:
        applied = list(executor.recorder.applied().get(app, []))
        nodes = {n.name: n for n in executor.loader.by_app().get(app, [])}
        for name in reversed(applied):
            if name == target:
                break
            executor.rollback(nodes[name], dry_run=options.get("dry_run", False), log=self._log(options))

    def _rollback_all(self, executor: MigrationExecutor, app: str | None, options: Any) -> None:
        applied = executor.recorder.applied()
        apps_to_roll = [app] if app else list(applied)
        for roll_app in apps_to_roll:
            nodes = {n.name: n for n in executor.loader.by_app().get(roll_app, [])}
            for name in reversed(list(applied.get(roll_app, []))):
                executor.rollback(nodes[name], dry_run=options.get("dry_run", False), log=self._log(options))
