"""Create/update tables for all installed apps (MiniDataAPI transform)."""

from __future__ import annotations

from typing import Any

from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Create or update tables declared by installed apps (TABLES in models.py)."

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.db import install_tables

        created = install_tables()
        if not created:
            self.stdout.write("No tables declared by installed apps.")
            return
        if options["verbosity"] >= 1:
            self.stdout.write(self.style.SUCCESS(f"Tables up to date ({len(created)}):"))
            for name in created:
                self.stdout.write(f"  {name}")
