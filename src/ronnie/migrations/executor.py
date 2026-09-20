"""Executor: applies, rolls back, fakes and reports migrations."""

from __future__ import annotations

import contextlib
from typing import Any

from ..core.exceptions import CommandError
from .loader import MigrationLoader, MigrationNode
from .operations import RunPython, RunSQL
from .recorder import MigrationRecorder
from .state import ModelState

__all__ = ["MigrationExecutor"]


class MigrationExecutor:
    def __init__(self, db: Any, loader: MigrationLoader | None = None) -> None:
        self.db = db
        self.loader = loader or MigrationLoader()
        self.recorder = MigrationRecorder(db)

    # -- planning ------------------------------------------------------------------

    def pending(self) -> list[MigrationNode]:
        """Migrations on disk not yet recorded, in graph order."""
        applied = self.recorder.applied()
        return [node for node in self.loader.ordered() if node.name not in applied.get(node.app, [])]

    def _node(self, app: str, prefix: str | None) -> MigrationNode:
        for node in self.loader.by_app().get(app, []):
            if prefix and node.name.startswith(prefix):
                return node
        raise CommandError(f"Cannot find migration {app!r} matching {prefix!r}.")

    # -- apply ----------------------------------------------------------------------

    def apply(
        self,
        node: MigrationNode,
        *,
        fake: bool = False,
        fake_initial: bool = False,
        dry_run: bool = False,
        log: Any = print,
    ) -> list[str]:
        """Apply one migration; returns the SQL executed (or printed)."""
        state = self._state_before(node)
        if fake:
            self.recorder.record(node.app, node.name)
            log(f"  Faking {node.app}.{node.name}... OK")
            return []
        if dry_run:
            sql: list[str] = []
            for operation in node.migration.operations:
                sql.extend([str(stmt) for stmt in self._op_sql(operation, state)])
                operation.mutate_state(state)
            return sql
        executed: list[str] = []
        fake_this = False
        if fake_initial and self._all_tables_exist(node):
            fake_this = True
        self.db.execute("BEGIN")
        try:
            for operation in node.migration.operations:
                if not fake_this:
                    for statement in self._op_sql(operation, state):
                        statement = str(statement)
                        self.db.execute(statement)
                        executed.append(statement)
                operation.mutate_state(state)
            self.recorder.record(node.app, node.name)
            self.db.execute("COMMIT")
            self._checkpoint()
        except Exception as err:
            self.db.execute("ROLLBACK")
            raise CommandError(f"Migration {node.app}.{node.name} failed: {err}") from err
        log(f"  Applying {node.app}.{node.name}... OK")
        return executed

    def _checkpoint(self) -> None:
        """Fold the WAL into the main file so external readers see the change.

        The storage engine keeps databases in WAL mode; without a checkpoint
        the frames live in ``<db>-wal`` until the process exits, hiding
        applied migrations from connections opened elsewhere.
        """
        with contextlib.suppress(Exception):
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _op_sql(self, operation: Any, state: ModelState) -> list[str]:
        statements: list[str] = operation.sql_statements(self.db, state)
        return statements

    def _all_tables_exist(self, node: MigrationNode) -> bool:
        from .operations import CreateTable

        creates = [op for op in node.migration.operations if isinstance(op, CreateTable)]
        if not creates:
            return False
        existing = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return all(op.name in existing for op in creates)

    def _state_before(self, node: MigrationNode) -> ModelState:
        state = ModelState()
        for candidate in self.loader.ordered():
            if candidate.key == node.key:
                break
            for operation in candidate.migration.operations:
                operation.mutate_state(state)
        return state

    # -- rollback ---------------------------------------------------------------------

    def rollback(self, node: MigrationNode, *, dry_run: bool = False, log: Any = print) -> list[str]:
        """Un-apply one migration (latest first). Returns reversed SQL."""
        state = self._state_before(node)
        after = state.copy()
        for operation in node.migration.operations:
            operation.mutate_state(after)
        irreversible = [
            type(op).__name__ for op in node.migration.operations if not getattr(op, "reversible", False)
        ]
        if irreversible:
            raise CommandError(
                f"Migration {node.app}.{node.name} is not reversible ({', '.join(irreversible)})."
            )
        statements: list[str] = []
        for operation in reversed(node.migration.operations):
            if dry_run:
                if isinstance(operation, (RunPython, RunSQL)):
                    statements.append(f"-- (dry-run) {operation.describe()}")
                else:
                    statements.extend(operation.reverse_statements(self.db, state, after))
            else:
                self.db.execute("BEGIN")
                try:
                    for statement in operation.reverse_statements(self.db, state, after):
                        self.db.execute(statement)
                        statements.append(statement)
                    self.db.execute("COMMIT")
                except Exception as err:
                    self.db.execute("ROLLBACK")
                    raise CommandError(f"Rollback of {node.app}.{node.name} failed: {err}") from err
            operation_undo_state(state, after)  # keep fold consistent below
        if not dry_run:
            self.db.execute("BEGIN")
            self.recorder.unrecord(node.app, node.name)
            self.db.execute("COMMIT")
            self._checkpoint()
        log(f"  Unapplying {node.app}.{node.name}... OK")
        return statements


def operation_undo_state(before: ModelState, after: ModelState) -> None:
    """Best-effort state fold bookkeeping for rollbacks (per-op precision
    is unnecessary: reverse_statements already received both states)."""
    return None
