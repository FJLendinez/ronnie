from __future__ import annotations

from typing import Any

from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Echo a message back (test fixture)."

    def add_arguments(self, parser):
        parser.add_argument("msg")
        parser.add_argument("--upper", action="store_true")

    def handle(self, *args: Any, **options: Any) -> str:
        msg = options["msg"]
        if options["upper"]:
            msg = msg.upper()
        return msg
