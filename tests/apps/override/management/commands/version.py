from __future__ import annotations

from typing import Any

from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Overrides the builtin version command (test fixture)."
    requires_environment = False
    requires_system_checks = ()

    def handle(self, *args: Any, **options: Any) -> str:
        return "OVERRIDDEN"
