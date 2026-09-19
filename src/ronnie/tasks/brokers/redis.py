"""RedisBroker: LPUSH/BRPOP queues (extra ``ronnie[redis]``)."""

from __future__ import annotations

from typing import Any

from .. import decode_message, encode_message


class RedisBroker:
    def __init__(self, url: str | None = None) -> None:
        self._url = url
        self._client: Any = None

    def _create_client(self) -> Any:
        try:
            import redis
        except ImportError as err:
            from ...core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured("RedisBroker needs redis-py: pip install 'ronnie[redis]'") from err
        from ...conf import settings

        url = self._url or str(
            getattr(settings._wrapped, "TASKS_BROKER_URL", None) or "redis://127.0.0.1:6379/0"
        )
        return redis.Redis.from_url(url)

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._create_client()
        return self._client

    @staticmethod
    def _key(queue: str) -> str:
        return f"ronnie.task.queue:{queue}"

    def enqueue(self, queue: str, message: dict[str, Any]) -> None:
        self.client.lpush(self._key(queue), encode_message(message))

    def dequeue(self, queues: list[str], timeout: float = 1.0) -> dict[str, Any] | None:
        keys = [self._key(q) for q in queues]
        result = self.client.brpop(keys, timeout=int(max(1, timeout)))
        if result is None:
            return None
        _key, payload = result
        return decode_message(payload.decode())
