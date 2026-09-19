"""Cryptographic signing — a compact, format-compatible ``django.core.signing``.

``Signer`` produces ``value[:timestamp]:signature`` strings using HMAC-SHA256
over a key derived as sha256(salt + key) — the same derivation and separator
conventions as Django, so signed values are interchangeable in format.

Never sign/serialize with pickle: this module only handles strings and JSON.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import time
from typing import Any

from ..core.exceptions import ImproperlyConfigured

__all__ = [
    "BadSignature",
    "SignatureExpired",
    "Signer",
    "TimestampSigner",
    "b64_decode",
    "b64_encode",
    "dumps",
    "loads",
]

# Separators may not contain base64-alphabet characters (or hash "$").
_UNSAFE_SEP_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_+=/$")


def b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class BadSignature(Exception):
    """The signature does not match (or the value is malformed)."""


class SignatureExpired(BadSignature):
    """The signature is valid but older than ``max_age``."""


def _get_keys() -> list[str]:
    from ..conf import settings

    keys = [settings.SECRET_KEY, *list(settings.SECRET_KEY_FALLBACKS)]
    if not any(keys):
        raise ImproperlyConfigured("SECRET_KEY must be set to sign values.")
    return keys


def _salt_hmac(salt: str, value: str, key: str, algorithm: str) -> str:
    # Django-compatible key derivation: sha256(salt + key)
    derived = hashlib.sha256((salt + key).encode()).digest()
    digestmod = getattr(hashlib, algorithm)
    sig = hmac.new(derived, value.encode(), digestmod).digest()
    return b64_encode(sig)


def _base36_encode(number: int) -> str:
    alphabet, base36 = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while number:
        number, i = divmod(number, 36)
        base36 = alphabet[i] + base36
    return base36 or "0"


def _base36_decode(value: str) -> int:
    return int(value, 36)


class Signer:
    """Sign strings: ``Signer().sign("v")`` → ``"v:signature"``."""

    def __init__(
        self,
        *,
        key: str | None = None,
        sep: str = ":",
        salt: str = "ronnie.core.signing",
        algorithm: str = "sha256",
        fallback_keys: list[str] | None = None,
    ) -> None:
        if not sep or any(c in _UNSAFE_SEP_CHARS for c in sep):
            raise ValueError("Unsafe signature separator; pick another character.")
        self.key = key
        self.salt = salt
        self.sep = sep
        self.algorithm = algorithm
        self._fallback_keys = fallback_keys

    def _signing_keys(self) -> list[str]:
        if self.key is not None:
            keys = [self.key, *(self._fallback_keys or [])]
        else:
            keys = _get_keys()
            if self._fallback_keys:
                keys += self._fallback_keys
        return [k for k in keys if k]

    def signature(self, value: str, key: str | None = None) -> str:
        keys = [key] if key is not None else self._signing_keys()
        return _salt_hmac(self.salt, value, keys[0], self.algorithm)

    def sign(self, value: str) -> str:
        return f"{value}{self.sep}{self.signature(value)}"

    def unsign(self, signed_value: str) -> str:
        if self.sep not in signed_value:
            raise BadSignature(f"No '{self.sep}' found in value")
        value, _, signature = signed_value.rpartition(self.sep)
        for key in self._signing_keys():
            if hmac.compare_digest(signature, self.signature(value, key)):
                return value
        raise BadSignature(f"Signature {signature!r} does not match")

    # -- object signing (JSON) ---------------------------------------------------

    def sign_object(self, obj: Any) -> str:
        return self.sign(b64_encode(json.dumps(obj).encode()))

    def unsign_object(self, payload: str) -> Any:
        return json.loads(b64_decode(self.unsign(payload)))


class TimestampSigner(Signer):
    """Sign strings with a timestamp: ``unsign(value, max_age=...)``."""

    def timestamp(self) -> str:
        return _base36_encode(int(time.time()))

    def sign(self, value: str) -> str:
        value = f"{value}{self.sep}{self.timestamp()}"
        return f"{value}{self.sep}{self.signature(value)}"

    def unsign(self, signed_value: str, max_age: int | dt.timedelta | None = None) -> str:
        result = super().unsign(signed_value)
        value, _, timestamp = result.rpartition(self.sep)
        try:
            timestamp_age = int(timestamp, 36)
        except ValueError:
            timestamp = timestamp[::-1]  # Django tolerates reversed base36
            timestamp_age = int(timestamp, 36)
        if max_age is not None:
            if isinstance(max_age, dt.timedelta):
                max_age_seconds = max_age.total_seconds()
            else:
                max_age_seconds = max_age
            age = time.time() - timestamp_age
            if age > max_age_seconds:
                raise SignatureExpired(f"Signature age {age:.0f}s > max_age {max_age_seconds:.0f}s")
        return value


def dumps(obj: Any, *, salt: str = "ronnie.core.signing") -> str:
    """Serialize + sign any JSON-compatible object into a URL-safe string."""
    return TimestampSigner(salt=salt).sign_object(obj)


def loads(
    payload: str, *, salt: str = "ronnie.core.signing", max_age: int | dt.timedelta | None = None
) -> Any:
    """Verify + deserialize a ``dumps()`` string (honouring ``max_age``)."""
    signer = TimestampSigner(salt=salt)
    return json.loads(b64_decode(signer.unsign(payload, max_age=max_age)))
