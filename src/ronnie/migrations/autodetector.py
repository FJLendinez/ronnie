"""Autodetector: diff live ``TABLES`` declarations against migration history."""

from __future__ import annotations

from typing import Any

from ..apps import apps as app_registry
from .loader import MigrationLoader
from .operations import AddField, AlterField, CreateTable, DeleteTable, RemoveField
from .state import ModelState, table_state_from_dataclass

__all__ = ["autodetect", "current_state", "detect_changes_for_app"]


def current_state() -> ModelState:
    """Model state as declared today: every installed app's TABLES."""
    state = ModelState()
    for config in app_registry.get_app_configs():
        module = config.models_module
        for cls in getattr(module, "TABLES", None) or []:
            spec = table_state_from_dataclass(cls, owner=config.label)
            state.add_table(spec)
    return state


def detect_changes_for_app(app: str, loader: MigrationLoader) -> list[Any]:
    """Operations needed to bring ``app``'s migrations up to its TABLES."""
    config = app_registry.get_app_config(app)
    declared = ModelState()
    for cls in getattr(config.models_module, "TABLES", None) or []:
        spec = table_state_from_dataclass(cls, owner=app)
        spec.owner = app
        declared.add_table(spec)

    historical = loader.app_state(app)
    operations: list[Any] = []

    for name, spec in declared.tables.items():
        if name not in historical.tables:
            operations.append(CreateTable(name=name, pk=spec.pk, fields=dict(spec.fields), owner=app))
            continue
        old = historical.tables[name]
        for field_name, field_spec in spec.fields.items():
            if field_name not in old.fields:
                pytype, default = field_spec
                operations.append(AddField(table=name, name=field_name, pytype=pytype, default=default))
            elif old.fields[field_name][0] != field_spec[0]:
                pytype, default = field_spec
                operations.append(AlterField(table=name, name=field_name, pytype=pytype, default=default))
        for field_name in old.fields:
            if field_name not in spec.fields and field_name != old.pk:
                operations.append(RemoveField(table=name, name=field_name))

    for name in historical.tables:
        if name not in declared.tables:
            operations.append(DeleteTable(name=name))

    return operations


def autodetect(loader: MigrationLoader, app_labels: list[str] | None = None) -> dict[str, list[Any]]:
    """Detect changes per app → {app: operations} (empty dicts omitted)."""
    if app_labels is None:
        app_labels = [c.label for c in app_registry.get_app_configs()]
    changes: dict[str, list[Any]] = {}
    for app in app_labels:
        app_changes = detect_changes_for_app(app, loader)
        if app_changes:
            changes[app] = app_changes
    return changes
