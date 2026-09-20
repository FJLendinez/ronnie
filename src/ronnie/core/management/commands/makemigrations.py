"""Detect model changes and write migration files."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.core.exceptions import CommandError
from ronnie.core.management import BaseCommand
from ronnie.migrations.autodetector import autodetect
from ronnie.migrations.loader import MigrationLoader
from ronnie.migrations.writer import migration_name_for, render_migration, write_migration


class Command(BaseCommand):
    help = "Detect model changes and create new migration files."
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("app_labels", nargs="*", help="Limit to these app labels.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be created, write nothing."
        )
        parser.add_argument("--empty", action="store_true", help="Create an empty migration (edit by hand).")
        parser.add_argument("--name", help="Custom migration name suffix.")
        parser.add_argument("--check", action="store_true", help="Exit non-zero if changes are detected.")

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.apps import apps

        labels = list(options.get("app_labels") or [])
        for label in labels:
            apps.get_app_config(label)  # validate: LookupError if unknown

        loader = MigrationLoader()
        changes = autodetect(loader, labels or None)
        if options.get("check"):
            if changes:
                for app, operations in changes.items():
                    for op in operations:
                        self.stdout.write(f"{app}: {op.describe()}")
                raise CommandError("Model changes require migrations.", returncode=1)
            self.stdout.write(self.style.SUCCESS("No changes detected."))
            return

        if options.get("empty"):
            from ronnie.apps import apps

            targets = labels or [c.label for c in apps.get_app_configs()]
            for label in targets:
                changes.setdefault(label, [])
        elif not changes:
            self.stdout.write("No changes detected.")
            return

        for app, operations in changes.items():
            app_path = loader.app_path(app)
            if app_path is None:
                raise CommandError(f"Cannot locate filesystem path for app {app!r}.")
            if options.get("empty"):
                operations = []
            number = loader.next_number(app)
            name = options.get("name") or ("initial" if number == 1 else migration_name_for(operations))
            dependencies = []
            nodes = loader.by_app().get(app, [])
            if nodes:
                dependencies.append((app, nodes[-1].name))
            content = render_migration(
                f"Auto-generated: {', '.join(op.describe() for op in operations) or 'empty'}",
                dependencies,
                operations,
            )
            if options.get("dry_run"):
                self.stdout.write(f"Would create {app}/migrations/{number:04d}_{name}.py:")
                self.stdout.write(content)
                continue
            target = write_migration(app_path, number, name, content)
            self.stdout.write(self.style.SUCCESS(f"Migrations for '{app}':"))
            self.stdout.write(f"  {target}")
            for op in operations:
                self.stdout.write(f"    - {op.describe()}")
