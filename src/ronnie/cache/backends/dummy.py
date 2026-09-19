"""A cache that caches nothing (for tests / feature switches)."""

from __future__ import annotations

from typing import Any

from ..base import BaseCache


class DummyCache(BaseCache):
    def _get(self, key: str) -> tuple[bool, Any]:
        return False, None

    def _set(self, key: str, value: Any, timeout: int | None) -> None:
        pass

    def _delete(self, key: str) -> None:
        pass

    def _has_key(self, key: str) -> bool:
        return False

    def _clear(self) -> None:
        pass

    def _incr(self, key: str, delta: int) -> int:
        raise ValueError(f"Key {key!r} not found")
