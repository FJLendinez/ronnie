"""Cache framework — ``caches["alias"]`` / ``cache`` (django.core.cache)."""

from __future__ import annotations

import importlib
from typing import Any

from ..core.exceptions import RonnieException
from .base import DEFAULT_TIMEOUT, BaseCache, CacheKeyWarning

__all__ = [
    "DEFAULT_TIMEOUT",
    "BaseCache",
    "CacheKeyWarning",
    "InvalidCacheBackendError",
    "cache",
    "caches",
]


class InvalidCacheBackendError(RonnieException):
    pass


class _Caches:
    """Lazy alias registry over the ``CACHES`` setting (thread-safe)."""

    def __init__(self) -> None:
        self._instances: dict[str, BaseCache] = {}

    def __getitem__(self, alias: str) -> BaseCache:
        alias = alias or "default"
        if alias not in self._instances:
            self._instances[alias] = self.create(alias)
        return self._instances[alias]

    def create(self, alias: str) -> BaseCache:
        from ..conf import settings

        configs = dict(getattr(settings._wrapped, "CACHES", None) or {})
        if alias not in configs:
            if alias == "default":
                configs["default"] = {"BACKEND": "ronnie.cache.backends.locmem.LocMemCache"}
            else:
                raise InvalidCacheBackendError(f"CACHES has no {alias!r} alias.")
        config = dict(configs[alias])
        backend_path = config.get("BACKEND")
        if not backend_path:
            raise InvalidCacheBackendError(f"CACHES[{alias!r}] needs a BACKEND.")
        module_path, _, attr = str(backend_path).rpartition(".")
        try:
            cls = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError) as exc:
            raise InvalidCacheBackendError(f"Cannot import cache backend {backend_path!r}: {exc}") from exc
        backend: BaseCache = cls(config)
        return backend

    def reset(self) -> None:
        """Test helper: drop cached instances (e.g. after overriding CACHES)."""
        self._instances.clear()


caches = _Caches()


class _DefaultCacheProxy:
    """``cache.get(...)`` delegates to ``caches['default']`` (lazy)."""

    def __getattr__(self, name: str) -> Any:
        return getattr(caches["default"], name)


cache = _DefaultCacheProxy()


def reset_caches() -> None:
    caches.reset()
