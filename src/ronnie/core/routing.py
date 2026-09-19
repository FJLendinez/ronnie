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


_HTTP_VERBS = frozenset(["get", "post", "put", "delete", "patch", "head", "trace", "options"])


def _implied_methods(entry: tuple[Any, ...]) -> frozenset[str]:
    """Resolve the HTTP methods a router entry registers (FastHTML rules).

    FastHTML decides in ``_add_route``: explicit methods win; a handler named
    ``get``/``post``/... on an explicit path maps to that verb only; anything
    else registers GET+POST.
    """
    methods, name = entry[2], entry[3]
    if methods:
        return frozenset([methods] if isinstance(methods, str) else methods)
    if name in _HTTP_VERBS:
        return frozenset([name])
    return frozenset({"get", "post"})


def mount_routers(app: Any, registry: Apps) -> list[str]:
    """Mount every app's routers onto ``app``; return the mounted route paths."""
    mounted: list[str] = []
    seen: dict[tuple[str, str], str] = {}  # (path, verb) -> app label
    for config in registry.get_app_configs():
        module = _import_optional(f"{config.name}.routes") or _import_optional(f"{config.name}.views")
        if module is None:
            continue
        routers = [obj for obj in vars(module).values() if isinstance(obj, APIRouter)]
        for router in routers:
            for entry in router.routes:
                path, func = entry[1], entry[0]
                verbs = _implied_methods(entry)
                clashes = sorted(v for v in verbs if (path, v) in seen)
                if clashes:
                    raise ImproperlyConfigured(
                        f"Duplicate route {path!r} ({', '.join(sorted(verbs))}) "
                        f"declared by apps {seen[(path, clashes[0])]!r} and {config.label!r}."
                    )
                for verb in verbs:
                    seen[(path, verb)] = config.label
                if getattr(func, "_ronnie_csrf_exempt", False):
                    from ..middleware.csrf import register_exempt_route

                    register_exempt_route(path)
            router.to_app(app)
            mounted.extend(entry[1] for entry in router.routes)
    return mounted
