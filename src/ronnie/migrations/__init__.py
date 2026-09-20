"""Ronnie's migration framework.

Migrations are versioned Python files under ``<app>/migrations/``:

::

    # apps/blog/migrations/0002_add_published_at.py
    from ronnie.migrations import AddField, MigrationBase

    class Migration(MigrationBase):
        dependencies = [("blog", "0001_initial")]

        operations = [
            AddField(table="post", name="published_at", pytype="datetime.date"),
        ]

Applied migrations are **stored** in the ``ronnie_migration`` table
(``app``, ``name``, ``applied_at``), so schema state is reproducible and
auditable:

- ``ronnie makemigrations`` — detect model changes, write migration files
- ``ronnie migrate`` — apply pending migrations (records each one)
- ``ronnie showmigrations`` — list applied/pending state ``[X]``/``[ ]``
- ``ronnie sqlmigrate app name`` — print the SQL a migration will run
"""

from __future__ import annotations

from typing import Any

from .operations import (
    AddField,
    AlterField,
    CreateTable,
    DeleteTable,
    Operation,
    RemoveField,
    RenameField,
    RunPython,
    RunSQL,
)

__all__ = [
    "AddField",
    "AlterField",
    "CreateTable",
    "DeleteTable",
    "MigrationBase",
    "Operation",
    "RemoveField",
    "RenameField",
    "RunPython",
    "RunSQL",
]


class MigrationBase:
    """Base class for migration files (alias ``Migration`` in generated files)."""

    dependencies: list[tuple[str, str]] = []
    operations: list[Any] = []
