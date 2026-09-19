"""Database access from the ``DATABASES`` setting (MiniDataAPI backends).

Engines:

- ``sqlite`` (default; uses fastlite, bundled with FastHTML)
- ``postgres`` (uses fastsql; install with ``ronnie[postgres]``)

Table convention: each app's ``models.py`` lists its row dataclasses in
``TABLES``; ``ronnie migrate`` creates/updates them with ``transform=True``.
"""

from __future__ import annotations

from typing import Any

from .core.exceptions import ImproperlyConfigured

__all__ = ["collect_tables", "get_database", "get_table", "install_tables"]

_databases: dict[str, Any] = {}
_tables: dict[tuple[str, type, str | None], Any] = {}


def get_database(alias: str = "default") -> Any:
    """Return (and cache) the MiniDataAPI database object for ``alias``."""
    from .conf import settings

    if alias in _databases:
        return _databases[alias]
    try:
        config = settings.DATABASES[alias]
    except (KeyError, AttributeError):
        raise ImproperlyConfigured(
            f"DATABASES has no {alias!r} alias (and DEBUG-mode fallbacks are disabled)."
        ) from None

    engine = str(config.get("ENGINE", "sqlite")).lower()
    name = config.get("NAME")
    if not name:
        raise ImproperlyConfigured(f"DATABASES[{alias!r}].NAME is required.")

    if engine in ("sqlite", "fastlite"):
        from fastlite import database

        db = database(str(name))
    elif engine in ("postgres", "postgresql", "fastsql"):
        try:
            from fastsql import Database
        except ImportError as err:
            raise ImproperlyConfigured(
                "The postgres engine needs the fastsql extra: pip install 'ronnie[postgres]'"
            ) from err
        db = Database(str(name))
    else:
        raise ImproperlyConfigured(f"Unknown database ENGINE {engine!r} (use 'sqlite' or 'postgres').")

    _databases[alias] = db
    return db


def collect_tables() -> list[tuple[str, type]]:
    """Return ``(app_label, table_cls)`` pairs from every installed app's models."""
    from .apps import apps

    if not apps.ready:
        import ronnie

        ronnie.setup()
    tables: list[tuple[str, type]] = []
    for config in apps.get_app_configs():
        module = config.models_module
        if module is None:
            continue
        for table in getattr(module, "TABLES", []):
            tables.append((config.label, table))
    return tables


def get_table(cls: type, alias: str = "default", pk: str | None = None) -> Any:
    """Return the MiniDataAPI table bound to a row dataclass (idempotent).

    Prefer this over ``database[cls]``: the object returned by ``create``
    carries the class binding needed for typed inserts and result rows.
    ``pk`` names the primary-key column; by default the class attribute
    ``pk_name`` is honoured, falling back to the ``id`` field.
    """
    pk = pk or getattr(cls, "pk_name", None)
    key = (alias, cls, pk)
    if key not in _tables:
        if pk is not None:
            _tables[key] = get_database(alias).create(cls, pk=pk, transform=True)
        else:  # implicit pk detection (the `id` field)
            _tables[key] = get_database(alias).create(cls, transform=True)
    return _tables[key]


def install_tables() -> list[str]:
    """Create/update every app table; return ``"label.Name"`` identifiers."""
    created = []
    for label, table in collect_tables():
        get_table(table)
        created.append(f"{label}.{table.__name__}")
    return created


def reset_databases_cache() -> None:
    """Test helper: drop cached connections (e.g. after swapping DATABASES)."""
    _databases.clear()
    _tables.clear()
