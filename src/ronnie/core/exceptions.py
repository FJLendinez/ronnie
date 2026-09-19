"""Exception hierarchy for Ronnie.

Mirrors django.core.exceptions where it makes sense.
"""

__all__ = [
    "RonnieException",
    "ImproperlyConfigured",
    "AppRegistryNotReady",
    "CommandError",
    "PermissionDenied",
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
