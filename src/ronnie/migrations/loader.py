"""Loader: discovers per-app migration files and orders them into a graph."""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

from ..apps import apps as app_registry
from .state import ModelState

__all__ = ["MigrationLoader", "MigrationNode"]

_NAME_RE = re.compile(r"^\d{4}_[a-z0-9_]+$")


class MigrationNode:
    """One migration file: app label, name, module path and Migration object."""

    def __init__(self, app: str, name: str, migration: Any) -> None:
        self.app = app
        self.name = name
        self.migration: Any = migration

    @property
    def key(self) -> tuple[str, str]:
        return (self.app, self.name)

    def __repr__(self) -> str:  # pragma: no cover - debug nicety
        return f"<Migration {self.app}.{self.name}>"


class MigrationLoader:
    """Reads ``<app>/migrations/*.py`` and builds the ordered migration graph."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], MigrationNode] = {}
        self._load()

    def _load(self) -> None:
        for config in app_registry.get_app_configs():
            if config.path is None:
                continue
            migrations_dir = config.path / "migrations"
            if not (migrations_dir / "__init__.py").is_file():
                continue
            names = sorted(p.stem for p in migrations_dir.glob("*.py") if _NAME_RE.match(p.stem))
            previous: str | None = None
            for name in names:
                module = importlib.import_module(f"{config.name}.migrations.{name}")
                migration = getattr(module, "Migration", None)
                if migration is None:
                    continue  # skip __init__ and non-migration helpers
                deps = [tuple(dep) for dep in getattr(migration, "dependencies", None) or []]
                if not deps and previous:
                    deps = [(config.label, previous)]
                migration.dependencies = deps
                self.nodes[(config.label, name)] = MigrationNode(config.label, name, migration)
                previous = name

    def by_app(self) -> dict[str, list[MigrationNode]]:
        out: dict[str, list[MigrationNode]] = {}
        for (app, _name), node in sorted(self.nodes.items()):
            out.setdefault(app, []).append(node)
        return out

    def ordered(self) -> list[MigrationNode]:
        """All migrations topologically ordered (dependencies first)."""
        ordered: list[MigrationNode] = []
        visiting: set[tuple[str, str]] = set()
        visited: set[tuple[str, str]] = set()

        def visit(key: tuple[str, str]) -> None:
            if key in visited or key in visiting:
                return
            visiting.add(key)
            node = self.nodes.get(key)
            if node is not None:
                for dep in getattr(node.migration, "dependencies", None) or []:
                    visit(dep)
            visiting.discard(key)
            visited.add(key)
            if node is not None:
                ordered.append(node)

        for key in sorted(self.nodes):
            visit(key)
        return ordered

    def project_state(self) -> ModelState:
        """Fold every known migration (applied or not) into a ModelState."""
        state = ModelState()
        for node in self.ordered():
            for operation in node.migration.operations:
                operation.mutate_state(state)
        return state

    def app_state(self, app: str) -> ModelState:
        """Fold only one app's migrations (state used by the autodetector)."""
        state = ModelState()
        for node in self.by_app().get(app, []):
            for operation in node.migration.operations:
                operation.mutate_state(state)
        return state

    def next_number(self, app: str) -> int:
        numbers = [int(node.name.split("_", 1)[0]) for node in self.by_app().get(app, [])]
        return (max(numbers) + 1) if numbers else 1

    def app_path(self, app: str) -> Path | None:
        try:
            config = app_registry.get_app_config(app)
        except LookupError:
            return None
        return config.path
