"""Create a Ronnie app directory structure."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ronnie.core.exceptions import CommandError
from ronnie.core.management import BaseCommand
from ronnie.core.management._templates import APP_TEMPLATE


class Command(BaseCommand):
    help = "Create a new app (routes.py, models.py, apps.py, ...)."
    requires_environment = False
    requires_system_checks = ()
    missing_args_message = "You must provide an app name."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name", help="App name (valid Python identifier).")
        parser.add_argument(
            "directory", nargs="?", help="Optional destination (default: apps/ if it exists)."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        name = options["name"]
        if not name.isidentifier():
            raise CommandError(f"{name!r} is not a valid app name.")

        if options["directory"]:
            base = Path(options["directory"])
        elif (Path.cwd() / "apps").is_dir():
            base = Path.cwd() / "apps"
        else:
            base = Path.cwd()

        target = base / name
        if target.exists():
            raise CommandError(f"'{target}' already exists.")

        # Apps created under an `apps/` package get the "apps.<name>" import path.
        app_name = f"apps.{name}" if base.name == "apps" else name
        class_name = "".join(part.capitalize() for part in name.split("_")) + "Config"

        context = {
            "app_name": app_name,
            "class_name": class_name,
            "label": name,
            "verbose_name": name.replace("_", " ").title(),
        }
        for rel_path, template in APP_TEMPLATE.items():
            path = target / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template.substitute(context))

        self.stdout.write(self.style.SUCCESS(f"App {name!r} created in {target}"))
        self.stdout.write(f"Remember to add {app_name!r} to INSTALLED_APPS.")
