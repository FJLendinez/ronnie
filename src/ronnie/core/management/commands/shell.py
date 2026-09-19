"""Open an interactive Python shell (IPython if available)."""

from __future__ import annotations

import argparse
import code
from typing import Any

from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Run an interactive Python shell with the Ronnie environment loaded."
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-i", "--interface", choices=("ipython", "python"), help="Preferred shell interface."
        )
        parser.add_argument("-c", "--command", help="Execute this command instead of opening a shell.")

    def handle(self, *args: Any, **options: Any) -> None:
        if command := options.get("command"):
            exec(command, {})  # explicit user opt-in, CLI context
            return
        if options.get("interface") != "python":
            try:
                from IPython import start_ipython  # type: ignore[import-not-found]
            except ImportError:
                pass
            else:
                start_ipython(argv=[])
                return
        code.interact(banner="Ronnie interactive shell", local=self._banner_vars())

    def _banner_vars(self) -> dict[str, Any]:
        import ronnie
        from ronnie import conf
        from ronnie.apps import apps as registry

        return {"ronnie": ronnie, "settings": conf.settings, "apps": registry}
