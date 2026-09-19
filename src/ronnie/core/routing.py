"""Routing integration — Ronnie's equivalent of Django per-app ``urls.py``.

Each installed app may define a ``routes.py`` (or ``views.py``) module.
Every ``Router`` instance found in the module namespace (definition order) is
mounted into the application automatically, with duplicate-path detection.
"""

from __future__ import annotations

import importlib
from typing import Any

from fasthtml.core import APIRouter, noop_body

from ..apps import Apps
from ..core.exceptions import ImproperlyConfigured

__all__ = ["Router", "mount_routers"]


class Router(APIRouter):  # type: ignore[misc]
    """An ``APIRouter`` with a normalized prefix (``Router("blog")`` → ``/blog``)."""

    def __init__(self, prefix: str = "", body_wrap: Any = noop_body) -> None:
        if prefix and not prefix.startswith("/"):
            prefix = f"/{prefix}"
        super().__init__(prefix=prefix or None, body_wrap=body_wrap)


def _import_optional(dotted: str) -> Any:
    try:
        return importlib.import_module(dotted)
    except ImportError as exc:
        if getattr(exc, "name", None) == dotted:
            return None  # module simply doesn't exist
        raise  # broken routes module: fail loudly


def mount_routers(app: Any, registry: Apps) -> list[str]:
    """Mount every app's routers onto ``app``; return the mounted route paths."""
    mounted: list[str] = []
    seen: dict[tuple[str, frozenset[str] | None], str] = {}
    for config in registry.get_app_configs():
        module = _import_optional(f"{config.name}.routes") or _import_optional(f"{config.name}.views")
        if module is None:
            continue
        routers = [obj for obj in vars(module).values() if isinstance(obj, APIRouter)]
        for router in routers:
            for entry in router.routes:
                _path, _methods = entry[1], entry[2]
                key = (_path, frozenset(_methods) if _methods else None)
                if key in seen:
                    raise ImproperlyConfigured(
                        f"Duplicate route {_path!r} (methods={_methods or 'default'}) "
                        f"declared by apps {seen[key]!r} and {config.label!r}."
                    )
                seen[key] = config.label
            router.to_app(app)
            mounted.extend(entry[1] for entry in router.routes)
    return mounted
