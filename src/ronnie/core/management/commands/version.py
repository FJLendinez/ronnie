"""Print the Ronnie version."""

from __future__ import annotations

from typing import Any

from ronnie import __version__
from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Show Ronnie's version."
    requires_environment = False
    requires_system_checks = ()

    def handle(self, *args: Any, **options: Any) -> str:
        return __version__
