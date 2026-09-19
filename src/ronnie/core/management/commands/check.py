"""Run system checks (add --deploy for deployment checks)."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.core import checks
from ronnie.core.exceptions import CommandError
from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Run system checks and report problems."
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--deploy", action="store_true", help="Include deployment-only checks.")
        parser.add_argument(
            "--tag",
            "-t",
            action="append",
            dest="tags",
            help="Run only checks labeled with this tag (repeatable).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        messages = checks.run_checks(
            tags=options.get("tags"),
            include_deployment_checks=options["deploy"],
        )
        for message in messages:
            style = self.style.ERROR if message.is_serious() else self.style.WARNING
            self.stdout.write(str(message), style_func=style)
        if errors := checks.get_error_count(messages):
            raise CommandError(f"System check identified {errors} error(s).", returncode=1)
        self.stdout.write(self.style.SUCCESS("System check identified no issues (0 silenced)."))
