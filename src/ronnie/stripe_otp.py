"""Ronnie's mirror of ``fasthtml.stripe_otp`` (optional: needs `stripe`).

Derives nothing when the dependency is missing — importing stays safe.
"""

from typing import Any

try:
    import fasthtml.stripe_otp as _source

    _names = list(getattr(_source, "__all__", None) or [])
    _names += [n for n in dir(_source) if not n.startswith("_") and n not in _names]
    for _name in _names:
        if _name not in globals():
            globals()[_name] = getattr(_source, _name)
    __all__ = [n for n in globals() if not n.startswith("_")]

    def __getattr__(name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        value = getattr(_source, name)
        globals()[name] = value
        return value

    def __dir__() -> list[str]:
        return sorted(set(__all__) | set(dir(_source)))

except ImportError:  # optional dependency not installed
    __all__ = []
