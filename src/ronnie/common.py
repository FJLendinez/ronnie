"""Ronnie's canonical curated import surface — the mirror of the FT common.

`ronnie.common` is deliberately **curated**, exactly like its counterpart:
the everyday vocabulary for handlers — components (`P`, `Titled`, `Form`,
`Input`, …), app factories (`fast_app`, `serve`, `FastHTML`), responses
(`Redirect`, `RedirectResponse`), request helpers and Ronnie's own additions
(`Router`, `CsrfToken`, `csrf_exempt`, `Alerts`, `HumanTime`)::

    from ronnie.common import P, Redirect, Router, Titled, serve

Everything else lives in the per-module mirrors, each a direct derivation of
its counterpart (`ronnie.core`, `ronnie.components`, `ronnie.svg`,
`ronnie.pico`, `ronnie.xtend`, `ronnie.oauth`, `ronnie.jupyter`,
`ronnie.live_reload`, `ronnie.toaster`, `ronnie.js`, `ronnie.ft`,
`ronnie.cli`, `ronnie.basics`, `ronnie.authmw`, `ronnie.fastapp`,
`ronnie.starlette`, `ronnie.stripe_otp`)::

    from ronnie.pico import Card, Grid
    from ronnie.svg import Circle, Svg
    from ronnie.oauth import GitHubAppClient

User code never imports ``fasthtml`` directly.
"""

from __future__ import annotations

import importlib as _importlib
from dataclasses import dataclass as dataclass
from typing import Any

from fastcore.utils import *  # noqa: F403 - same derivation as the source
from fastcore.xml import *  # noqa: F403

# Composed from Ronnie's own mirrors, in the source composition order.
from .authmw import *  # noqa: F403
from .basics import *  # noqa: F403
from .fastapp import *  # noqa: F403
from .js import *  # noqa: F403
from .live_reload import *  # noqa: F403
from .starlette import *  # noqa: F403
from .toaster import *  # noqa: F403

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
# imports above already bound (APIRouter, noop_body).
from .core.routing import Router as Router  # noqa: E402
