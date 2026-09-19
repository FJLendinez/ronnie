"""Exception hierarchy for Ronnie.

Mirrors django.core.exceptions where it makes sense.
"""

__all__ = [
    "AppRegistryNotReady",
    "CommandError",
    "ImproperlyConfigured",
    "PermissionDenied",
    "RonnieException",
]


class RonnieException(Exception):
    """Base class for all Ronnie exceptions."""


class ImproperlyConfigured(RonnieException):
    """Ronnie is somehow improperly configured."""


class AppRegistryNotReady(RonnieException):
    """The app registry has not been populated yet."""


class CommandError(RonnieException):
    """A management command failed in a controlled way.

    Carries an optional ``returncode`` used by the CLI to ``sys.exit()``.
    """

    def __init__(self, *args: object, returncode: int = 1) -> None:
        self.returncode = returncode
        super().__init__(*args)


class PermissionDenied(RonnieException):
    """The user does not have permission to do something."""


class ValidationError(RonnieException):
    """Validation failed; ``messages`` holds a list of error strings."""

    def __init__(self, messages: str | list[str]) -> None:
        self.messages = [messages] if isinstance(messages, str) else list(messages)
        super().__init__("; ".join(self.messages))
