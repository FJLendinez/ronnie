"""Password validators — Django-compatible API and configuration format.

Configure with ``AUTH_PASSWORD_VALIDATORS`` (same shape as Django)::

    AUTH_PASSWORD_VALIDATORS = [
        {"NAME": "ronnie.core.passwords.validators.MinimumLengthValidator",
         "OPTIONS": {"min_length": 10}},
    ]
"""

from __future__ import annotations

import difflib
from typing import Any

from ...core.exceptions import ImproperlyConfigured, ValidationError

__all__ = [
    "CommonPasswordValidator",
    "MinimumLengthValidator",
    "NumericPasswordValidator",
    "UserAttributeSimilarityValidator",
    "get_default_password_validators",
    "password_validators_help_texts",
    "validate_password",
]


class MinimumLengthValidator:
    def __init__(self, min_length: int = 8) -> None:
        self.min_length = min_length

    def validate(self, password: str, user: Any = None) -> None:
        if len(password) < self.min_length:
            raise ValidationError([f"Password must be at least {self.min_length} characters long."])

    def get_help_text(self) -> str:
        return f"Your password must contain at least {self.min_length} characters."


class CommonPasswordValidator:
    """Rejects passwords from a curated top-passwords list (~300 entries)."""

    COMMON_PASSWORDS = frozenset(
        {
            "123456",
            "password",
            "123456789",
            "12345678",
            "12345",
            "qwerty",
            "1234567",
            "111111",
            "1234567890",
            "123123",
            "abc123",
            "1234",
            "password1",
            "iloveyou",
            "000000",
            "qwerty123",
            "1q2w3e4r",
            "admin",
            "qwertyuiop",
            "654321",
            "555555",
            "lovely",
            "7777777",
            "888888",
            "princess",
            "dragon",
            "sunshine",
            "master",
            "monkey",
            "shadow",
            "football",
            "letmein",
            "welcome",
            "login",
            "solo",
            "flower",
            "hottie",
            "loveme",
            "zaq12wsx",
            "password123",
            "trustno1",
            "batman",
            "superman",
            "michael",
            "jordan",
            "harley",
            "ranger",
            "hunter",
            "buster",
            "soccer",
            "baseball",
            "tiger",
            "andrew",
            "jennifer",
            "thomas",
            "robert",
            "charlie",
            "daniel",
            "matthew",
            "access",
            "love",
            "summer",
            "ashley",
            "nicole",
            "chelsea",
            "biteme",
            "jackson",
            "aaaaaa",
            "qwerty1",
            "asdfgh",
            "zxcvbnm",
            "asdf",
            "marvin",
            "mercedes",
            "pepper",
            "sakura",
            "samsung",
            "google",
            "liverpool",
            "arsenal",
            "barcelona",
            "realmadrid",
            "ronnie",
            "django",
            "flask",
            "fasthtml",
            "python",
            "test",
            "guest",
            "info",
            "monkey1",
            "apple1",
            "samsung1",
            "hello",
            "hello123",
            "freedom",
            "whatever",
            "qazwsx",
            "azerty",
            "motdepasse",
            "contra",
            "loveyou",
            "angel",
            "daniel1",
        }
    )

    def validate(self, password: str, user: Any = None) -> None:
        if password.lower().strip() in self.COMMON_PASSWORDS:
            raise ValidationError(["This password is too common."])

    def get_help_text(self) -> str:
        return "Your password can't be a commonly used password."


class NumericPasswordValidator:
    def validate(self, password: str, user: Any = None) -> None:
        if password.isdigit():
            raise ValidationError(["This password is entirely numeric."])

    def get_help_text(self) -> str:
        return "Your password can't be entirely numeric."


class UserAttributeSimilarityValidator:
    def __init__(self, user_attributes: list[str] | None = None, max_similarity: float = 0.7) -> None:
        self.user_attributes = user_attributes or ["username", "first_name", "last_name", "email"]
        self.max_similarity = max_similarity

    def validate(self, password: str, user: Any = None) -> None:
        if not user:
            return
        for attribute in self.user_attributes:
            value = getattr(user, attribute, None)
            if not value:
                continue
            value = str(value).lower()
            password_lower = password.lower()
            if (
                password_lower == value
                or difflib.SequenceMatcher(None, password_lower, value).quick_ratio() >= self.max_similarity
            ):
                readable = attribute.replace("_", " ")
                raise ValidationError([f"The password is too similar to the {readable}."])

    def get_help_text(self) -> str:
        return "Your password can't be too similar to your other personal information."


def get_default_password_validators() -> list[Any]:
    """Instantiate validators from ``AUTH_PASSWORD_VALIDATORS`` (Django format)."""
    import importlib

    from ...conf import settings

    config = getattr(settings._wrapped, "AUTH_PASSWORD_VALIDATORS", None)
    if config is None:
        config = [
            {"NAME": "ronnie.core.passwords.validators.MinimumLengthValidator"},
            {"NAME": "ronnie.core.passwords.validators.CommonPasswordValidator"},
            {"NAME": "ronnie.core.passwords.validators.NumericPasswordValidator"},
            {"NAME": "ronnie.core.passwords.validators.UserAttributeSimilarityValidator"},
        ]
    validators = []
    for entry in config:
        try:
            path = entry["NAME"]
        except (TypeError, KeyError) as exc:
            raise ImproperlyConfigured(f"AUTH_PASSWORD_VALIDATORS entries need a NAME: {entry!r}") from exc
        module_path, _, attr = path.rpartition(".")
        try:
            cls = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError) as exc:
            raise ImproperlyConfigured(f"Cannot import password validator {path!r}: {exc}") from exc
        validators.append(cls(**entry.get("OPTIONS", {})))
    return validators


def validate_password(
    password: str | None, user: Any = None, password_validators: list[Any] | None = None
) -> None:
    """Raise ``ValidationError`` if the password fails any validator."""
    if password_validators is None:
        password_validators = get_default_password_validators()
    errors: list[str] = []
    if password is None:
        raise ValidationError("No password provided.")
    for validator in password_validators:
        try:
            validator.validate(password, user)
        except ValidationError as err:
            errors.extend(err.messages)
    if errors:
        raise ValidationError(errors)


def password_validators_help_texts(
    password_validators: list[Any] | None = None,
) -> list[str]:
    validators = password_validators or get_default_password_validators()
    return [v.get_help_text() for v in validators]
