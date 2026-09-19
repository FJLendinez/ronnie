"""Create a Ronnie project directory structure."""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path
from typing import Any

from ronnie.core.exceptions import CommandError
from ronnie.core.management import BaseCommand
from ronnie.core.management._templates import PROJECT_TEMPLATE


def generate_secret_key(length: int = 50) -> str:
    """Return a random secret key (hex, like Django's get_random_string)."""
    return secrets.token_hex(length // 2)


class Command(BaseCommand):
    help = "Create a new Ronnie project (manage.py, config/settings.py, ...)."
    requires_environment = False
    requires_system_checks = ()
    missing_args_message = "You must provide a project name."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name", help="Project name (valid Python identifier).")
        parser.add_argument("directory", nargs="?", help="Optional destination directory.")

    def handle(self, *args: Any, **options: Any) -> None:
        name = options["name"]
        if not name.isidentifier():
            raise CommandError(f"{name!r} is not a valid project name.")

        base = Path(options["directory"]) if options["directory"] else Path.cwd()
        target = base / name
        if target.exists() and any(target.iterdir()):
            raise CommandError(f"'{target}' already exists and is not empty.")

        context = {
            "project_name": name,
            "secret_key": generate_secret_key(),
            "settings_module": f"{name}.config.settings",
            "first_app": "blog",
        }
        for rel_path, template in PROJECT_TEMPLATE.items():
            path = target / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template.substitute(context))
        manage = target / "manage.py"
        manage.chmod(manage.stat().st_mode | 0o755)

        self.stdout.write(self.style.SUCCESS(f"Project {name!r} created in {target}"))
        self.stdout.write("Next steps:")
        self.stdout.write(f"  cd {target}")
        self.stdout.write("  python manage.py runserver")
