"""Delete expired sessions from server-side engines."""

from __future__ import annotations

from typing import Any

from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Delete expired sessions (db engine; run from cron."

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.conf import settings
        from ronnie.contrib.sessions.engines import DbSessionEngine, resolve_engine

        engine = resolve_engine(settings.SESSION_ENGINE)
        if not isinstance(engine, DbSessionEngine):
            self.stdout.write("SESSION_ENGINE keeps no server-side rows; nothing to clear.")
            return
        removed = engine.clear_expired()
        if options["verbosity"] >= 1:
            self.stdout.write(self.style.SUCCESS(f"Deleted {removed} expired session(s)."))
