"""BaseCache — the cache API contract (django.core.cache.backends.base)."""

from __future__ import annotations

import pickle
import threading
from typing import Any

__all__ = ["DEFAULT_TIMEOUT", "BaseCache", "CacheKeyWarning"]

DEFAULT_TIMEOUT: int | None = 300  # seconds; None = never expire
MAX_KEY_LENGTH = 250


class CacheKeyWarning(Warning):
    pass


def default_key_func(key: str, key_prefix: str, version: int) -> str:
    return f"{key_prefix}:{version}:{key}"


class BaseCache:
    """Subclasses implement the ``_*`` primitives; everything else derives.

    ``params`` comes from ``CACHES``: ``LOCATION``, ``TIMEOUT``,
    ``OPTIONS`` (``MAX_ENTRIES``, ``CULL_FREQUENCY``), ``KEY_PREFIX``,
    ``VERSION``, ``KEY_FUNCTION``.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        options = params.get("OPTIONS") or {}
        self._max_entries = int(options.get("MAX_ENTRIES", 300))
        self._cull_frequency = int(options.get("CULL_FREQUENCY", 3))
        timeout = params.get("TIMEOUT", DEFAULT_TIMEOUT)
        self._timeout: int | None = None if timeout is None else int(timeout)
        self._key_prefix = str(params.get("KEY_PREFIX", ""))
        self._version = int(params.get("VERSION", 1))

        key_func_path = params.get("KEY_FUNCTION")
        if key_func_path:
            import importlib

            module_path, _, attr = str(key_func_path).rpartition(".")
            self._key_func = getattr(importlib.import_module(module_path), attr)
        else:
            self._key_func = default_key_func

    # -- keys -----------------------------------------------------------------------

    def make_key(self, key: str, version: int | None = None) -> str:
        key = str(key)
        self.validate_key(key)
        built = self._key_func(key, self._key_prefix, self._version if version is None else version)
        return str(built)

    def validate_key(self, key: str) -> None:
        if len(key) > MAX_KEY_LENGTH:
            raise CacheKeyWarning(f"Cache key exceeds {MAX_KEY_LENGTH} chars (len={len(key)}).")
        if " " in key:
            import warnings

            warnings.warn(f"Cache key contains spaces: {key!r}", CacheKeyWarning, stacklevel=2)

    def get_backend_timeout(self, timeout: int | None = DEFAULT_TIMEOUT) -> int | None:
        if timeout is DEFAULT_TIMEOUT:
            return self._timeout
        return None if timeout is None else int(timeout)

    # -- primitives (override) ---------------------------------------------------------

    def _get(self, key: str) -> tuple[bool, Any]:
        raise NotImplementedError

    def _set(self, key: str, value: Any, timeout: int | None) -> None:
        raise NotImplementedError

    def _delete(self, key: str) -> None:
        raise NotImplementedError

    def _has_key(self, key: str) -> bool:
        found, _ = self._get(key)
        return found

    def _clear(self) -> None:
        raise NotImplementedError

    def _incr(self, key: str, delta: int) -> int:
        found, value = self._get(key)
        if not found:
            raise ValueError(f"Key {key!r} not found")
        value += delta
        self._set(key, value, self._timeout)
        return int(value)

    # -- public API ----------------------------------------------------------------------

    def add(self, key: str, value: Any, timeout: int | None = DEFAULT_TIMEOUT) -> bool:
        key = self.make_key(key)
        if self._has_key(key):
            return False
        self._set(key, value, self.get_backend_timeout(timeout))
        return True

    def get(self, key: str, default: Any = None, version: int | None = None) -> Any:
        found, value = self._get(self.make_key(key, version))
        return value if found else default

    def set(
        self, key: str, value: Any, timeout: int | None = DEFAULT_TIMEOUT, version: int | None = None
    ) -> None:
        self._set(self.make_key(key, version), value, self.get_backend_timeout(timeout))

    def touch(self, key: str, timeout: int | None = DEFAULT_TIMEOUT, version: int | None = None) -> bool:
        key = self.make_key(key, version)
        if not self._has_key(key):
            return False
        _, value = self._get(key)
        self._set(key, value, self.get_backend_timeout(timeout))
        return True

    def delete(self, key: str, version: int | None = None) -> bool:
        existed = self._has_key(self.make_key(key, version))
        self._delete(self.make_key(key, version))
        return existed

    def get_or_set(
        self, key: str, default: Any, timeout: int | None = DEFAULT_TIMEOUT, version: int | None = None
    ) -> Any:
        key = self.make_key(key, version)
        found, value = self._get(key)
        if found:
            return value
        if callable(default):
            default = default()
        self._set(key, default, self.get_backend_timeout(timeout))
        return default

    def get_many(self, keys: list[str], version: int | None = None) -> dict[str, Any]:
        out = {}
        for key in keys:
            found, value = self._get(self.make_key(key, version))
            if found:
                out[key] = value
        return out

    def set_many(
        self, data: dict[str, Any], timeout: int | None = DEFAULT_TIMEOUT, version: int | None = None
    ) -> None:
        for key, value in data.items():
            self._set(self.make_key(key, version), value, self.get_backend_timeout(timeout))

    def delete_many(self, keys: list[str], version: int | None = None) -> None:
        for key in keys:
            self._delete(self.make_key(key, version))

    def incr(self, key: str, delta: int = 1, version: int | None = None) -> int:
        return int(self._incr(self.make_key(key, version), delta))

    def decr(self, key: str, delta: int = 1, version: int | None = None) -> int:
        return self._incr(self.make_key(key, version), -delta)

    def has_key(self, key: str, version: int | None = None) -> bool:
        return self._has_key(self.make_key(key, version))

    def clear(self) -> None:
        self._clear()

    def close(self, **kwargs: Any) -> None:
        pass


class PickleMixin:
    """Helpers for backends that store pickled payloads."""

    def dumps(self, value: Any) -> bytes:
        return pickle.dumps(value, pickle.HIGHEST_PROTOCOL)

    def loads(self, raw: bytes) -> Any:
        return pickle.loads(raw)


class LockMixin:
    def _make_lock(self) -> threading.Lock:
        return threading.Lock()
