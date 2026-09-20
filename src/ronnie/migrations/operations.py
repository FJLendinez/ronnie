"""Migration operations: each mutates a ModelState and knows its SQL.

Structural operations are pure data (serializable by the writer); RunPython
and RunSQL are escape hatches for hand-written migrations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .state import ModelState, TableSpec, field_sql_type, sql_literal

if TYPE_CHECKING:
    pass

__all__ = [
    "AddField",
    "AlterField",
    "CreateTable",
    "DeleteTable",
    "Operation",
    "RemoveField",
    "RenameField",
    "RunPython",
    "RunSQL",
]


class Operation:
    """Base operation: subclasses implement state mutation + SQL."""

    reversible: bool = False

    def mutate_state(self, state: ModelState) -> None:
        raise NotImplementedError

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        """DDL/DML for this operation given the state *before* it runs."""
        raise NotImplementedError

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        raise NotImplementedError(f"Operation {type(self).__name__} is not reversible.")

    def describe(self) -> str:
        return type(self).__name__


# -- structural ----------------------------------------------------------------------


class CreateTable(Operation):
    reversible = True

    def __init__(self, name: str, pk: str | None, fields: dict[Any, Any], owner: str = "") -> None:
        self.name = name
        self.pk = pk
        self.fields = fields
        self.owner = owner

    def spec(self) -> TableSpec:
        return TableSpec(self.name, self.pk, self.fields, self.owner)

    def mutate_state(self, state: ModelState) -> None:
        state.add_table(self.spec())

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        return [self.spec().ddl()]

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        return [f"DROP TABLE [{self.name}];"]

    def describe(self) -> str:
        return f"Create table {self.name}"


class DeleteTable(Operation):
    reversible = True

    def __init__(self, name: str) -> None:
        self.name = name

    def mutate_state(self, state: ModelState) -> None:
        state.tables.pop(self.name, None)

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        return [f"DROP TABLE [{self.name}];"]

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        return [before[self.name].ddl()]

    def describe(self) -> str:
        return f"Delete table {self.name}"


class AddField(Operation):
    reversible = True

    def __init__(self, table: str, name: str, pytype: str = "str", default: Any = None) -> None:
        self.table = table
        self.name = name
        self.pytype = pytype
        self.default = default

    def mutate_state(self, state: ModelState) -> None:
        state[self.table].fields[self.name] = (self.pytype, self.default)

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        ddl = f"ALTER TABLE [{self.table}] ADD COLUMN [{self.name}] {field_sql_type(self.pytype)}"
        if self.default is not None:
            ddl += f" DEFAULT {sql_literal(self.default)}"
        return [ddl + ";"]

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        return [f"ALTER TABLE [{self.table}] DROP COLUMN [{self.name}];"]

    def describe(self) -> str:
        return f"Add field {self.name} to {self.table}"


class RemoveField(Operation):
    reversible = True

    def __init__(self, table: str, name: str) -> None:
        self.table = table
        self.name = name

    def mutate_state(self, state: ModelState) -> None:
        state[self.table].fields.pop(self.name, None)

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        return [f"ALTER TABLE [{self.table}] DROP COLUMN [{self.name}];"]

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        pytype, default = before[self.table].fields[self.name]
        add = AddField(self.table, self.name, pytype, default)
        return add.sql_statements(db, before)

    def describe(self) -> str:
        return f"Remove field {self.name} from {self.table}"


class RenameField(Operation):
    reversible = True

    def __init__(self, table: str, old_name: str, new_name: str) -> None:
        self.table = table
        self.old_name = old_name
        self.new_name = new_name

    def mutate_state(self, state: ModelState) -> None:
        fields = state[self.table].fields
        items = [(self.new_name if k == self.old_name else k, v) for k, v in fields.items()]
        state[self.table].fields = dict(items)

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        return [f"ALTER TABLE [{self.table}] RENAME COLUMN [{self.old_name}] TO [{self.new_name}];"]

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        return [f"ALTER TABLE [{self.table}] RENAME COLUMN [{self.new_name}] TO [{self.old_name}];"]

    def describe(self) -> str:
        return f"Rename field {self.old_name} → {self.new_name} on {self.table}"


class AlterField(Operation):
    """Change a column's type/default — implemented as an sqlite table rebuild."""

    reversible = True

    def __init__(self, table: str, name: str, pytype: str = "str", default: Any = None) -> None:
        self.table = table
        self.name = name
        self.pytype = pytype
        self.default = default

    def mutate_state(self, state: ModelState) -> None:
        state[self.table].fields[self.name] = (self.pytype, self.default)

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        old = before[self.table]
        target = old.copy()
        target.fields[self.name] = (self.pytype, self.default)
        return _rebuild_statements(old, target)

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        old = before[self.table]
        current = after[self.table]
        target = current.copy()
        target.fields[self.name] = old.fields[self.name]
        return _rebuild_statements(current, target)

    def describe(self) -> str:
        return f"Alter field {self.name} on {self.table}"


def _rebuild_statements(source: TableSpec, target: TableSpec) -> list[str]:
    shared = [c for c in target.column_names() if c in source.column_names()]
    temp = f"__ronnie_rebuild_{target.name}"
    statements = [
        target.ddl().replace(f"[{target.name}]", f"[{temp}]", 1),
        f"INSERT INTO [{temp}] ({', '.join(f'[{c}]' for c in shared)}) "
        f"SELECT {', '.join(f'[{c}]' for c in shared)} FROM [{source.name}];",
        f"DROP TABLE [{source.name}];",
        f"ALTER TABLE [{temp}] RENAME TO [{target.name}];",
    ]
    return statements


# -- escape hatches --------------------------------------------------------------------


class RunPython(Operation):
    """Run a callable ``fn(db)`` (hand-written migrations only)."""

    def __init__(
        self, code: Callable[[Any], None], reverse_code: Callable[[Any], None] | None = None
    ) -> None:
        self.code = code
        self.reverse_code = reverse_code

    @property
    def reversible(self) -> bool:  # type: ignore[override]
        return self.reverse_code is not None

    def mutate_state(self, state: ModelState) -> None:  # data-only op
        return None

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        self.code(db)
        return []

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        if self.reverse_code is None:
            raise NotImplementedError("RunPython without reverse_code.")
        self.reverse_code(db)
        return []

    def describe(self) -> str:
        return f"RunPython {getattr(self.code, '__name__', self.code)!r}"


class RunSQL(Operation):
    def __init__(self, sql: str, reverse_sql: str | None = None) -> None:
        self.sql = sql
        self.reverse_sql = reverse_sql

    @property
    def reversible(self) -> bool:  # type: ignore[override]
        return self.reverse_sql is not None

    def mutate_state(self, state: ModelState) -> None:
        return None

    def sql_statements(self, db: Any, before: ModelState) -> list[str]:
        return [self.sql]

    def reverse_statements(self, db: Any, before: ModelState, after: ModelState) -> list[str]:
        if self.reverse_sql is None:
            raise NotImplementedError("RunSQL without reverse_sql.")
        return [self.reverse_sql]

    def describe(self) -> str:
        return f"RunSQL {self.sql[:40]!r}…"
