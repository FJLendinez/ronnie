"""Redis cache backend (extra ``ronnie[redis]``).

``LOCATION`` is a redis:// URL. Tests inject a client by subclassing and
overriding ``_create_client`` (e.g. fakeredis).
"""

from __future__ import annotations

from typing import Any

from ..base import BaseCache


class RedisCache(BaseCache):
    def __init__(self, params: dict[str, Any] | None = None) -> None:
        super().__init__(params)
        self._location = str((params or {}).get("LOCATION") or "redis://127.0.0.1:6379/0")
        self._client: Any = None

    def _create_client(self) -> Any:
        try:
            import redis
        except ImportError as err:
            from ...core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured("The redis cache needs redis-py: pip install 'ronnie[redis]'") from err
        return redis.Redis.from_url(self._location)

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _get(self, key: str) -> tuple[bool, Any]:
        raw = self.client.get(key)
        if raw is None:
            return False, None
        import pickle

        return True, pickle.loads(raw)

    def _set(self, key: str, value: Any, timeout: int | None) -> None:
        import pickle

        payload = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
        if timeout is None:
            self.client.set(key, payload)
        else:
            self.client.setex(key, timeout, payload)

    def _delete(self, key: str) -> None:
        self.client.delete(key)

    def _has_key(self, key: str) -> bool:
        return bool(self.client.exists(key))

    def _clear(self) -> None:
        self.client.flushdb()

    def _incr(self, key: str, delta: int) -> int:
        # Values are stored pickled, so load-modify-store (not client.incr).
        found, value = self._get(key)
        if not found:
            raise ValueError(f"Key {key!r} not found")
        value += delta
        self._set(key, value, self._timeout)
        return int(value)
