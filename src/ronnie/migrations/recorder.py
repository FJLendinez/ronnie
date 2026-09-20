"""Migration recorder — the ``ronnie_migration`` table storing applied state."""

from __future__ import annotations

import datetime as dt
from typing import Any

__all__ = ["RECORDER_TABLE", "MigrationRecorder"]

RECORDER_TABLE = "ronnie_migration"

_DDL = f"""
CREATE TABLE IF NOT EXISTS [{RECORDER_TABLE}] (
   [id] INTEGER PRIMARY KEY,
   [app] TEXT NOT NULL,
   [name] TEXT NOT NULL,
   [applied_at] TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS [idx_{RECORDER_TABLE}_app_name]
   ON [{RECORDER_TABLE}] ([app], [name]);
"""


class MigrationRecorder:
    """Stores which migrations have been applied (the migration history)."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def ensure_table(self) -> None:
        self.db.execute(_DDL)

    def applied(self) -> dict[str, list[str]]:
        """Map of app → ordered list of applied migration names."""
        self.ensure_table()
        rows = list(self.db.execute(f"SELECT [app], [name] FROM [{RECORDER_TABLE}] ORDER BY [app], [id]"))
        out: dict[str, list[str]] = {}
        for app, name in rows:
            out.setdefault(str(app), []).append(str(name))
        return out

    def record(self, app: str, name: str) -> None:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        self.db.execute(
            f"INSERT INTO [{RECORDER_TABLE}] ([app], [name], [applied_at]) VALUES (?, ?, ?)",
            [app, name, now],
        )

    def unrecord(self, app: str, name: str) -> None:
        self.db.execute(
            f"DELETE FROM [{RECORDER_TABLE}] WHERE [app] = ? AND [name] = ?",
            [app, name],
        )
