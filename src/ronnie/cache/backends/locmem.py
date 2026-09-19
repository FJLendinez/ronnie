"""Thread-safe in-process cache with expiry and LRU-ish culling."""

from __future__ import annotations

import threading
import time
from typing import Any

from ..base import BaseCache


class LocMemCache(BaseCache):
    def __init__(self, params: dict[str, Any] | None = None, *, name: str = "default") -> None:
        super().__init__(params)
        self._name = str((params or {}).get("LOCATION") or name)
        self._store: dict[str, tuple[float | None, Any]] = {}
        self._lock = threading.Lock()

    def _expired(self, entry: tuple[float | None, Any]) -> bool:
        expires, _ = entry
        return expires is not None and expires <= time.time()

    def _get(self, key: str) -> tuple[bool, Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False, None
            if self._expired(entry):
                del self._store[key]
                return False, None
            return True, entry[1]

    def _set(self, key: str, value: Any, timeout: int | None) -> None:
        with self._lock:
            if len(self._store) >= self._max_entries:
                self._cull()
            expires = (time.time() + timeout) if timeout is not None else None
            self._store[key] = (expires, value)

    def _cull(self) -> None:
        """Expire stale entries; still full → drop ~1/CULL_FREQUENCY of keys."""
        now = time.time()
        self._store = {k: v for k, v in self._store.items() if v[0] is None or v[0] > now}
        if len(self._store) >= self._max_entries and self._cull_frequency:
            doomed = list(self._store)[:: self._cull_frequency]
            for key in doomed:
                del self._store[key]

    def _delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def _has_key(self, key: str) -> bool:
        found, _ = self._get(key)
        return found

    def _clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _incr(self, key: str, delta: int) -> int:
        with self._lock:
            entry = self._store.get(key)
            if entry is None or self._expired(entry):
                raise ValueError(f"Key {key!r} not found")
            value = entry[1] + delta
            self._store[key] = (entry[0], value)
            return int(value)
