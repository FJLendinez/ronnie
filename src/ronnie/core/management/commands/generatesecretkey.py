"""Generate a random SECRET_KEY (Django's generatesecretkey equivalent)."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.core.management import BaseCommand
from ronnie.core.management.commands.startproject import generate_secret_key


class Command(BaseCommand):
    help = "Print a random secret key suitable for SECRET_KEY."
    requires_environment = False
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--length", type=int, default=50, help="Key length in characters (default 50).")

    def handle(self, *args: Any, **options: Any) -> str:
        return generate_secret_key(options["length"])
