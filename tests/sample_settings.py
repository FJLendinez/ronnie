"""Sample project settings module used by the settings tests."""

DEBUG = True
SECRET_KEY = "test-secret-key"
CUSTOM_VALUE = "custom"
INSTALLED_APPS: list[str] = []

_CALLS = {"n": 0}


def COMPUTED_SETTING() -> int:
    _CALLS["n"] += 1
    return 21 * 2


def CALL_COUNT() -> int:
    return _CALLS["n"]
