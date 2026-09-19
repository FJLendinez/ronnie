"""File-based cache: one pickled file per key under LOCATION (atomic writes)."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from ..base import BaseCache


class FileBasedCache(BaseCache):
    def __init__(self, params: dict[str, Any] | None = None) -> None:
        super().__init__(params)
        location = str((params or {}).get("LOCATION") or tempfile.gettempdir())
        self._dir = Path(location)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.md5(key.encode()).hexdigest()
        return self._dir / f"ronnie-cache-{digest}.cache"

    def _get(self, key: str) -> tuple[bool, Any]:
        import pickle

        path = self._path(key)
        try:
            raw = path.read_bytes()
            expires, value = pickle.loads(raw)
        except (OSError, pickle.PickleError, EOFError):
            return False, None
        if expires is not None and expires <= time.time():
            self._delete(key)
            return False, None
        return True, value

    def _set(self, key: str, value: Any, timeout: int | None) -> None:
        import pickle

        expires = (time.time() + timeout) if timeout is not None else None
        payload = pickle.dumps((expires, value), pickle.HIGHEST_PROTOCOL)
        fd, tmp_name = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(payload)
            os.replace(tmp_name, self._path(key))  # atomic on POSIX
        except OSError:
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
        if len(self) >= self._max_entries:
            self._cull()

    def __len__(self) -> int:
        return sum(1 for _ in self._dir.glob("ronnie-cache-*.cache"))

    def _cull(self) -> None:
        self._remove_expired()
        files = sorted(self._dir.glob("ronnie-cache-*.cache"), key=lambda p: p.stat().st_mtime)
        if len(files) >= self._max_entries and self._cull_frequency:
            for path in files[:: self._cull_frequency]:
                path.unlink(missing_ok=True)

    def _remove_expired(self) -> None:
        import pickle

        now = time.time()
        for path in self._dir.glob("ronnie-cache-*.cache"):
            try:
                expires, _ = pickle.loads(path.read_bytes())
                if expires is not None and expires <= now:
                    path.unlink(missing_ok=True)
            except (OSError, pickle.PickleError, EOFError):
                path.unlink(missing_ok=True)

    def _delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _clear(self) -> None:
        for path in self._dir.glob("ronnie-cache-*.cache"):
            path.unlink(missing_ok=True)
