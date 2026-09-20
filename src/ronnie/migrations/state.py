"""Schema state model: tables, fields and DDL mapping for migrations.

A ``ModelState`` is a serializable snapshot of the tables an app owns —
what migration files record and what the autodetector diffs against the
live ``TABLES`` declarations.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

__all__ = ["ModelState", "TableSpec", "field_sql_type", "table_state_from_dataclass"]

# Field spec: name -> (python type as string, default literal or None)
FieldSpec = dict[str, tuple[str, Any]]


def field_sql_type(pytype: str) -> str:
    """Map a Python annotation string to its SQL column type (sqlite)."""
    base = pytype.replace(" | None", "").replace("|None", "").strip()
    return {
        "int": "INTEGER",
        "bool": "INTEGER",
        "float": "FLOAT",
        "str": "TEXT",
        "bytes": "BLOB",
        "datetime.date": "TEXT",
        "datetime.datetime": "TEXT",
        "date": "TEXT",
        "datetime": "TEXT",
    }.get(base, "TEXT")


class TableSpec:
    """One table: name, primary key column (or None) and field specs."""

    def __init__(self, name: str, pk: str | None, fields: FieldSpec, owner: str = "") -> None:
        self.name = name
        self.pk = pk
        self.fields: FieldSpec = dict(fields)
        self.owner = owner

    def column_names(self) -> list[str]:
        return list(self.fields)

    def copy(self) -> TableSpec:
        return TableSpec(self.name, self.pk, dict(self.fields), self.owner)

    def ddl(self) -> str:
        cols: list[str] = []
        for name, (pytype, default) in self.fields.items():
            column = f"[{name}] {field_sql_type(pytype)}"
            if name == self.pk:
                column += " PRIMARY KEY"
            elif default is not None:
                column += f" DEFAULT {sql_literal(default)}"
            cols.append(column)
        return f"CREATE TABLE [{self.name}] (\n   " + ",\n   ".join(cols) + "\n)"

    def __repr__(self) -> str:  # pragma: no cover - debug nicety
        return f"TableSpec({self.name!r}, pk={self.pk!r}, fields={self.fields!r})"


def sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


class ModelState:
    """Ordered mapping of table name → TableSpec for one app (or all apps)."""

    def __init__(self) -> None:
        self.tables: dict[str, TableSpec] = {}

    def add_table(self, spec: TableSpec) -> None:
        self.tables[spec.name] = spec

    def copy(self) -> ModelState:
        state = ModelState()
        for spec in self.tables.values():
            state.add_table(spec.copy())
        return state

    def __contains__(self, name: str) -> bool:
        return name in self.tables

    def __getitem__(self, name: str) -> TableSpec:
        return self.tables[name]


def _annotation_str(annotation: Any) -> str:
    if isinstance(annotation, type):
        if annotation is dt.date or annotation is dt.datetime:
            return f"datetime.{annotation.__name__}"
        return annotation.__name__
    return str(annotation)


def table_state_from_dataclass(cls: type, owner: str = "") -> TableSpec:
    """Build a TableSpec the way the MiniDataAPI would create the table.

    Mirrors the storage engine's conventions: table name is the lowercased
    class name; primary key is ``pk_name`` when declared, else an ``id``
    field, else an implicit ``id`` rowid alias.
    """
    name = cls.__name__.lower()
    pk = getattr(cls, "pk_name", None)
    fields: FieldSpec = {}
    for field in dataclasses.fields(cls):
        default: Any = None
        if field.default is not dataclasses.MISSING:
            default = field.default
        elif field.default_factory is not dataclasses.MISSING:
            default = field.default_factory()
        if isinstance(default, (list, dict, set)):
            default = None  # non-literal defaults are not DDL material
        fields[field.name] = (_annotation_str(field.type), default)
    if pk is None and "id" in fields:
        pk = "id"
    if pk is None:
        fields = {"id": ("int", None), **fields}
        pk = "id"
    return TableSpec(name, pk, fields, owner=owner)
