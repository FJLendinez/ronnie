"""Ronnie's canonical import surface.

Everything you need to write handlers — FT components (HTML and SVG),
themes, OAuth clients, notebook helpers, response objects, app factories —
is imported from here::

    from ronnie.common import P, Titled, Redirect, serve, Card, Circle

This module derives the **entire** underlying FT package: every public name
of every importable ``fasthtml.*`` submodule is re-exported (the curated
``fasthtml.common`` surface first, then ``components``, ``core``, ``svg``,
``pico``, ``xtend``, ``oauth``, ``jupyter``, ``live_reload``, ``cli`` and
the rest; submodules whose optional dependencies are missing — e.g.
``stripe_otp`` — are skipped). On top of that derivation Ronnie adds its own
components and helpers (``Router``, ``CsrfToken``, ``csrf_exempt``,
``Alerts``, ``HumanTime``, …), resolved lazily to keep the import graph
acyclic. User code never imports ``fasthtml`` directly.
"""

from __future__ import annotations

import importlib as _importlib
import pkgutil as _pkgutil
from typing import Any

import fasthtml as _fasthtml
from fasthtml.common import *  # noqa: F403 - curated core of the derivation

#: Submodules successfully derived (introspection; ``_``-prefixed and
#: optional-dependency modules excluded).
_DERIVED_SUBMODULES: list[str] = ["common"]

for _info in sorted(_pkgutil.iter_modules(_fasthtml.__path__), key=lambda m: m.name):
    _name = _info.name
    if _name.startswith("_") or _name == "common":
        continue  # internals and the already-starred curated surface
    try:
        _module = _importlib.import_module(f"fasthtml.{_name}")
    except ImportError:  # optional dependency not installed (e.g. stripe_otp)
        continue
    _DERIVED_SUBMODULES.append(_name)
    for _attr in dir(_module):
        if _attr.startswith("_") or _attr in globals():  # first wins: common rules
            continue
        globals()[_attr] = getattr(_module, _attr)

__all__ = [name for name in globals() if not name.startswith("_")]

# Ronnie additions: name → module that provides it. Resolved on first access
# so that this module never imports Ronnie packages at import time (those
# packages themselves import from `ronnie.common`).
_LAZY_EXPORTS: dict[str, str] = {
    "CsrfToken": "ronnie.middleware.csrf",
    "csrf_token": "ronnie.middleware.csrf",
    "csrf_exempt": "ronnie.middleware.csrf",
    "hx_csrf_headers": "ronnie.middleware.csrf",
    "Alerts": "ronnie.contrib.messages",
    "HumanTime": "ronnie.contrib.humanize",
}
__all__ += list(_LAZY_EXPORTS)
__all__.sort()


def derived_submodules() -> list[str]:
    """The fasthtml submodules this surface derives from, in order."""
    return list(_DERIVED_SUBMODULES)


def __getattr__(name: str) -> Any:
    """PEP 562: resolve Ronnie's own exports lazily."""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module 'ronnie.common' has no attribute {name!r}")
    value = getattr(_importlib.import_module(module_path), name)
    globals()[name] = value  # cache: subsequent accesses skip the import
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))


# Imported last: Ronnie's Router shadows the ASGI-level Router that the
# derived surface re-exports. Safe because routing only needs names the star
# import already bound (APIRouter, noop_body).
from .core.routing import Router as Router  # noqa: E402
