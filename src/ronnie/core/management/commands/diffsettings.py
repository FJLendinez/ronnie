"""Show settings that differ from Ronnie's global defaults."""

from __future__ import annotations

from typing import Any

from ronnie import global_settings
from ronnie.conf import settings
from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "List settings differing from the built-in defaults."
    requires_system_checks = ()

    def handle(self, *args: Any, **options: Any) -> None:
        wrapped = settings._wrapped
        if wrapped is None:
            self.stderr.write("Settings are not configured.")
            return
        for name in sorted(dir(wrapped)):
            if not name.isupper() or name == "SETTINGS_MODULE":
                continue
            value = getattr(wrapped, name)
            default = getattr(global_settings, name, _MISSING)
            if value != default:
                self.stdout.write(f"{name} = {value!r}")


class _MISSING:
    def __repr__(self) -> str:
        return "<no default>"
