"""Ronnie's mirror of ``fasthtml.toaster`` — direct derivation.

Exposes every public attribute of the source module: its ``__all__`` order
first, then the rest of the public namespace, and any name the source
resolves lazily (its own PEP 562 ``__getattr__``). Import from here instead
of the underlying package.
"""

from typing import Any

import fasthtml.toaster as _source

_names = list(getattr(_source, "__all__", None) or [])
_names += [n for n in dir(_source) if not n.startswith("_") and n not in _names]
for _name in _names:
    if _name not in globals():
        globals()[_name] = getattr(_source, _name)

__all__ = [n for n in globals() if not n.startswith("_")]


def __getattr__(name: str) -> Any:
    """Names the source resolves lazily (not listed in dir()/__all__)."""
    if name.startswith("_"):
        raise AttributeError(name)
    value = getattr(_source, name)  # may raise AttributeError — faithful
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(dir(_source)))
