"""Ronnie's canonical import surface.

Everything you need to write handlers — FT components, response helpers,
app factories — is imported from here::

    from ronnie.common import P, Titled, Redirect, serve

This module is a direct derivation of the underlying FT stack: every public
name of ``fasthtml.common`` is re-exported, plus Ronnie's own components and
helpers (``Router``, ``CsrfToken``, ``csrf_exempt``, ``Alerts``,
``HumanTime``, …), which resolve lazily to keep the import graph acyclic.
User code never imports ``fasthtml`` directly.
"""

from __future__ import annotations

import importlib
from typing import Any

import fasthtml.common as _fasthtml_common
from fasthtml.common import *  # noqa: F403 - the derived surface

__all__ = [name for name in dir(_fasthtml_common) if not name.startswith("_")]

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

# Imported last: Ronnie's Router shadows the ASGI-level Router that the
# derived surface re-exports. Safe because routing only needs names the star
# import already bound (APIRouter, noop_body).
from .core.routing import Router as Router  # noqa: E402


def __getattr__(name: str) -> Any:
    """PEP 562: resolve Ronnie's own exports lazily."""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module 'ronnie.common' has no attribute {name!r}")
    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value  # cache: subsequent accesses skip the import
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
