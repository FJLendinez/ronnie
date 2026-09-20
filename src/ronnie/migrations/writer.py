"""Writer: renders detected operations into a migration file on disk."""

from __future__ import annotations

import pprint
import re
from pathlib import Path

from .operations import (
    AddField,
    AlterField,
    CreateTable,
    DeleteTable,
    Operation,
    RemoveField,
    RenameField,
)

__all__ = ["migration_name_for", "render_migration", "write_migration"]

_HEADER = '''"""{doc}"""

from ronnie.migrations import {imports}


class Migration(MigrationBase):
    dependencies = {dependencies}

    operations = [
{operations}
    ]
'''


def migration_name_for(operations: list[Operation], custom: str | None = None) -> str:
    if custom:
        return custom
    if not operations:
        return "empty"
    first = operations[0]
    if isinstance(first, CreateTable):
        return f"create_{first.name}"
    if isinstance(first, DeleteTable):
        return f"delete_{first.name}"
    if isinstance(first, AddField):
        return f"add_{first.name}"
    if isinstance(first, RemoveField):
        return f"remove_{first.name}"
    if isinstance(first, RenameField):
        return f"rename_{first.old_name}"
    if isinstance(first, AlterField):
        return f"alter_{first.name}"
    return "auto"


def _render_op(operation: Operation) -> str:
    if isinstance(operation, CreateTable):
        fields = pprint.pformat(operation.fields, width=68, sort_dicts=False)
        indented = "\n".join("            " + line for line in fields.splitlines())
        return (
            f"        CreateTable(\n"
            f'            name="{operation.name}",\n'
            f"            pk={operation.pk!r},\n"
            f"            fields={indented.lstrip()},\n"
            f'            owner="{operation.owner}",\n'
            f"        ),"
        )
    if isinstance(operation, DeleteTable):
        return f'        DeleteTable(name="{operation.name}"),'
    if isinstance(operation, AddField):
        return (
            f'        AddField(table="{operation.table}", name="{operation.name}", '
            f"pytype={operation.pytype!r}, default={operation.default!r}),"
        )
    if isinstance(operation, RemoveField):
        return f'        RemoveField(table="{operation.table}", name="{operation.name}"),'
    if isinstance(operation, RenameField):
        return (
            f'        RenameField(table="{operation.table}", '
            f'old_name="{operation.old_name}", new_name="{operation.new_name}"),'
        )
    if isinstance(operation, AlterField):
        return (
            f'        AlterField(table="{operation.table}", name="{operation.name}", '
            f"pytype={operation.pytype!r}, default={operation.default!r}),"
        )
    raise TypeError(f"Cannot auto-write {type(operation).__name__}; edit the file by hand.")


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "auto"


def render_migration(doc: str, dependencies: list[tuple[str, str]], operations: list[Operation]) -> str:
    used = {type(op).__name__ for op in operations}
    imports = ", ".join(sorted(used)) or "Migration"
    if "MigrationBase" not in imports:
        imports = f"MigrationBase, {imports}"
    deps = pprint.pformat([tuple(dep) for dep in dependencies], width=68)
    body = "\n".join(_render_op(op) for op in operations) or "        # no operations"
    return _HEADER.format(
        doc=doc,
        imports=imports,
        dependencies=deps,
        operations=body,
    )


def write_migration(app_path: Path, number: int, name: str, content: str) -> Path:
    """Ensure ``migrations/`` exists and write ``NNNN_name.py``."""
    migrations_dir = app_path / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    init_file = migrations_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Migrations for this app."""\n')
    file_name = f"{number:04d}_{_slug(name)}.py"
    target = migrations_dir / file_name
    target.write_text(content)
    return target
