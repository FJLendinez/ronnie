"""Start a development server with auto-reload (uvicorn)."""

from __future__ import annotations

import argparse
from typing import Any

from ronnie.conf import settings
from ronnie.core.exceptions import CommandError
from ronnie.core.management import BaseCommand

DEFAULT_ADDR, DEFAULT_PORT = "127.0.0.1", 8000


class Command(BaseCommand):
    help = "Start the development server (uvicorn with auto-reload)."
    # Dev convenience: don't block the server on check warnings.
    requires_system_checks = ()

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("addrport", nargs="?", help="Optional [ip:]port, e.g. 0.0.0.0:8000.")
        parser.add_argument("--noreload", action="store_true", help="Disable auto-reload.")

    def handle(self, *args: Any, **options: Any) -> None:
        import uvicorn

        host, port = self._parse_addrport(options.get("addrport"))
        app_path = self._asgi_app_path()
        if options["verbosity"] >= 1:
            self.stdout.write(
                self.style.NOTICE(
                    f"Serving {app_path} at http://{host}:{port} "
                    f"(reload {'off' if options['noreload'] else 'on'})"
                )
            )
        uvicorn.run(
            app_path,
            host=host,
            port=port,
            reload=not options["noreload"],
            log_level="warning" if options["verbosity"] < 2 else "info",
        )

    def _parse_addrport(self, addrport: str | None) -> tuple[str, int]:
        if not addrport:
            return DEFAULT_ADDR, DEFAULT_PORT
        if ":" in addrport:
            host, _, port = addrport.rpartition(":")
        else:
            host, port = DEFAULT_ADDR, addrport
        try:
            return host or DEFAULT_ADDR, int(port)
        except ValueError:
            raise CommandError(f"Invalid port: {port!r}") from None

    def _asgi_app_path(self) -> str:
        module = settings.SETTINGS_MODULE or ""
        if not module:
            raise CommandError("RONNIE_SETTINGS_MODULE is not set.")
        package = module.rsplit(".", 1)[0]
        return f"{package}.asgi:application"
