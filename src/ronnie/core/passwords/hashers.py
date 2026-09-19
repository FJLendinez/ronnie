"""Password hashing — Django-format compatible hashers.

Stored format: ``<algorithm>$<params>$<salt>$<hash>`` (e.g.
``pbkdf2_sha256$1000000$ab12..cd34$base64hash``), so hashes produced by
Django verify here and vice versa. ``PASSWORD_HASHERS[0]`` encodes new
passwords; all listed hashers verify.

Hashers (stdlib only by default):

- ``pbkdf2_sha256`` (default encoder)
- ``scrypt`` (verify + optional encoder)
- ``argon2`` via the ``ronnie[argon2]`` extra (argon2-cffi)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Any, ClassVar

from ...core.exceptions import ImproperlyConfigured

__all__ = [
    "UNUSABLE_PASSWORD_PREFIX",
    "Argon2PasswordHasher",
    "PBKDF2PasswordHasher",
    "ScryptPasswordHasher",
    "check_password",
    "get_hashers",
    "identify_hasher",
    "is_password_usable",
    "make_password",
]

UNUSABLE_PASSWORD_PREFIX = "!"  # matches Django
ALGORITHM_NAME = "!"


class BasePasswordHasher:
    """Abstract hasher: subclasses implement encode() and must verify()."""

    algorithm: ClassVar[str]
    digest_name: ClassVar[str] = "sha256"

    def salt(self) -> str:
        return secrets.token_hex(16)  # 128 bits, hex

    def encode(self, password: str, salt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def verify(self, password: str, encoded: str) -> bool:
        return hmac.compare_digest(encoded, self.encode(password, *self._split(encoded)))

    def _split(self, encoded: str) -> tuple[str, ...]:
        parts = encoded.split("$", 2)
        return (parts[1],) if len(parts) == 3 else ()


class PBKDF2PasswordHasher(BasePasswordHasher):
    """PBKDF2 with SHA-256 (hashlib.pbkdf2_hmac), Django's default."""

    algorithm = "pbkdf2_sha256"
    iterations = 1_000_000
    digest_name = "sha256"

    def encode(self, password: str, salt: str, iterations: int | None = None) -> str:
        iterations = iterations or self.iterations
        dk = hashlib.pbkdf2_hmac(self.digest_name, password.encode(), salt.encode(), iterations)
        return f"{self.algorithm}${iterations}${salt}${base64.b64encode(dk).decode()}"

    def verify(self, password: str, encoded: str) -> bool:
        try:
            _, iterations, salt, _ = encoded.split("$", 3)
            return hmac.compare_digest(encoded, self.encode(password, salt, int(iterations)))
        except ValueError:
            return False

    def must_update(self, encoded: str) -> bool:
        try:
            return int(encoded.split("$", 3)[1]) != self.iterations
        except (ValueError, IndexError):
            return False

    def harden_runtime(self, password: str, encoded: str) -> None:
        # Equalize timing when a weaker hash was used (Django parity).
        _, iterations, salt, _ = encoded.split("$", 3)
        extra = self.iterations - int(iterations)
        if extra > 0:
            hashlib.pbkdf2_hmac(self.digest_name, password.encode(), salt.encode(), extra)


class ScryptPasswordHasher(BasePasswordHasher):
    """scrypt (OpenSSL-backed hashlib.scrypt)."""

    algorithm = "scrypt"
    work_factor = 2**15
    block_size = 8
    parallelism = 1
    maxmem = 64 * 1024 * 1024 * 4

    def encode(self, password: str, salt: str) -> str:
        dk = hashlib.scrypt(
            password.encode(),
            salt=salt.encode(),
            n=self.work_factor,
            r=self.block_size,
            p=self.parallelism,
            maxmem=self.maxmem,
            dklen=32,
        )
        return (
            f"{self.algorithm}${self.work_factor}${self.block_size}"
            f"${self.parallelism}${salt}${base64.b64encode(dk).decode()}"
        )

    def verify(self, password: str, encoded: str) -> bool:
        try:
            _, n, r, p, salt, _ = encoded.split("$", 5)
            dk = hashlib.scrypt(
                password.encode(),
                salt=salt.encode(),
                n=int(n),
                r=int(r),
                p=int(p),
                maxmem=self.maxmem,
                dklen=32,
            )
            expected = encoded.rsplit("$", 1)[1]
            return hmac.compare_digest(base64.b64encode(dk).decode(), expected)
        except ValueError:
            return False


class Argon2PasswordHasher(BasePasswordHasher):
    """Argon2id via argon2-cffi (extra ``ronnie[argon2]``)."""

    algorithm = "argon2"

    def __init__(self) -> None:
        try:
            from argon2 import PasswordHasher
        except ImportError as err:
            raise ImproperlyConfigured(
                "Argon2PasswordHasher needs argon2-cffi: pip install 'ronnie[argon2]'"
            ) from err
        self._hasher = PasswordHasher()

    def encode(self, password: str, salt: str) -> str:
        # argon2-cffi manages its own salts; the salt argument is ignored.
        return f"{self.algorithm}${self._hasher.hash(password)}"

    def verify(self, password: str, encoded: str) -> bool:
        from argon2.exceptions import VerifyMismatchError

        try:
            return bool(self._hasher.verify(encoded.split("$", 1)[1], password))
        except VerifyMismatchError:
            return False
        except ValueError:
            return False


_BUILTIN = {
    "pbkdf2_sha256": PBKDF2PasswordHasher,
    "scrypt": ScryptPasswordHasher,
    "argon2": Argon2PasswordHasher,
}


def get_hashers() -> list[BasePasswordHasher]:
    """Instantiate the hashers listed in ``PASSWORD_HASHERS`` (order matters)."""
    from ...conf import settings

    paths = list(getattr(settings._wrapped, "PASSWORD_HASHERS", None) or [])
    if not paths:
        paths = [
            "ronnie.core.passwords.hashers.PBKDF2PasswordHasher",
            "ronnie.core.passwords.hashers.ScryptPasswordHasher",
        ]
    hashers: list[BasePasswordHasher] = []
    for path in paths:
        if "." not in path:
            raise ImproperlyConfigured(f"PASSWORD_HASHERS entries must be paths: {path!r}")
        module_path, _, attr = path.rpartition(".")
        import importlib

        try:
            cls = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError) as exc:
            raise ImproperlyConfigured(f"Cannot import hasher {path!r}: {exc}") from exc
        hasher = cls() if isinstance(cls, type) else cls
        hashers.append(hasher)
    return hashers


def identify_hasher(encoded: str) -> BasePasswordHasher:
    algorithm = encoded.split("$", 1)[0]
    for hasher in get_hashers():
        if hasher.algorithm == algorithm:
            return hasher
    raise ValueError(f"Unknown password hash algorithm {algorithm!r}.")


def make_password(password: str | None, salt: str | None = None, hasher: str = "default") -> str:
    """Hash a password (or produce an unusable hash for ``None``)."""
    if password is None:
        return UNUSABLE_PASSWORD_PREFIX + secrets.token_hex(16)
    hashers = get_hashers()
    target = hashers[0] if hasher == "default" else _find(hashers, hasher)
    return target.encode(password, salt or target.salt())


def check_password(password: str | None, encoded: str) -> bool:
    """Verify a password against a stored hash (never raises for bad input)."""
    if password is None or not is_password_usable(encoded):
        return False
    try:
        return identify_hasher(encoded).verify(password, encoded)
    except ValueError:
        return False


def is_password_usable(encoded: str | None) -> bool:
    return encoded is not None and not encoded.startswith(UNUSABLE_PASSWORD_PREFIX)


def _find(hashers: list[BasePasswordHasher], algorithm: str) -> Any:
    for hasher in hashers:
        if hasher.algorithm == algorithm:
            return hasher
    raise ImproperlyConfigured(f"Unknown hasher algorithm {algorithm!r}.")
