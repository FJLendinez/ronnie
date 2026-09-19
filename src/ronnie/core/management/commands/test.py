"""Run tests with pytest (``ronnie test`` / ``python manage.py test``)."""

from __future__ import annotations

from typing import Any

from ronnie.core.exceptions import CommandError
from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Run the test suite with pytest."
    requires_system_checks = ()
    requires_environment = False  # tests boot settings themselves (isolation)

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("args", nargs="*", help="Arguments passed to pytest.")
        parser.add_argument(
            "--failfast", action="store_true", help="Stop on first failure (maps to pytest -x)."
        )
        parser.add_argument(
            "--keepdb", action="store_true", help="No-op (Ronnie always uses throwaway sqlite DBs)."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            import pytest
        except ImportError as err:
            raise CommandError("pytest is required: pip install pytest (or 'ronnie[dev]')") from err

        pytest_args = list(options.get("args", []))
        if options.get("failfast"):
            pytest_args.insert(0, "-x")
        if options.get("verbosity", 1) >= 2:
            pytest_args.insert(0, "-vv")
        elif options.get("verbosity", 1) == 0:
            pytest_args.insert(0, "-q")

        exit_code = pytest.main(pytest_args)
        if exit_code != 0:
            raise CommandError(f"Tests failed (pytest exit {exit_code}).", returncode=exit_code)
