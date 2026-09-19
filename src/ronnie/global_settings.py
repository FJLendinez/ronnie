"""Global defaults for Ronnie settings.

Equivalent of ``django/conf/global_settings.py``. Every project settings
module overrides values from here; ``ronnie diffsettings`` shows the diff.
Only UPPERCASE attributes are considered settings.
"""

__all__ = [
    "ALLOWED_HOSTS",
    "DEBUG",
    "DEFAULT_CHARSET",
    "INSTALLED_APPS",
    "LANGUAGE_CODE",
    "MIDDLEWARE",
    "SECRET_KEY",
    "SECRET_KEY_FALLBACKS",
    "STATIC_URL",
    "TIME_ZONE",
    "USE_TZ",
]

# Core
DEBUG = False
DEFAULT_CHARSET = "utf-8"
TIME_ZONE = "UTC"
USE_TZ = True
LANGUAGE_CODE = "en"

# Security (see SECURITY_SETTINGS.md / plan §7)
SECRET_KEY = ""
SECRET_KEY_FALLBACKS: list[str] = []
ALLOWED_HOSTS: list[str] = []

# Applications & middleware (strings = dotted paths, resolvable & overridable)
INSTALLED_APPS: list[str] = []
MIDDLEWARE: list[str] = []

# Static files served by the dev server (and an ASGI mount in prod)
STATIC_URL = "/static"
STATIC_ROOT: str | None = None  # e.g. BASE_DIR / "static"; mounted when the dir exists

# Logging: None → Ronnie's DEFAULT_LOGGING; dict → passed to logging.config.dictConfig
LOGGING: dict[str, "object"] | None = None

# Sessions (cookie-based signed sessions until contrib.sessions is installed)
SESSION_COOKIE_NAME = "ronnie_session"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2  # two weeks, in seconds
SESSION_COOKIE_SAMESITE = "lax"
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_DOMAIN: str | None = None
