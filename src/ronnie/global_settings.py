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
MIDDLEWARE: list[str] = [
    "ronnie.middleware.security.SecurityMiddleware",
    "ronnie.middleware.host.HostValidationMiddleware",
    "ronnie.contrib.sessions.middleware.SessionMiddleware",
    "ronnie.middleware.csrf.CsrfMiddleware",
    "ronnie.contrib.auth.middleware.AuthMiddleware",
    "ronnie.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Static files served by the dev server (and an ASGI mount in prod)
STATIC_URL = "/static"
STATIC_ROOT: str | None = None  # e.g. BASE_DIR / "static"; mounted when the dir exists

# Logging: None → Ronnie's DEFAULT_LOGGING; dict → passed to logging.config.dictConfig
LOGGING: dict[str, "object"] | None = None

# Security headers & TLS (django.middleware.security parity)
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_SSL_REDIRECT = False
SECURE_SSL_HOST: str | None = None
SECURE_REDIRECT_EXEMPT: list[str] = []
SECURE_PROXY_SSL_HEADER: tuple[str, str] | None = None
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Host header validation
USE_X_FORWARDED_HOST = False

# Clickjacking
X_FRAME_OPTIONS = "DENY"

# CSRF
CSRF_COOKIE_NAME = "csrftoken"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_TRUSTED_ORIGINS: list[str] = []
CSRF_EXEMPT_PATHS: list[str] = []

# Passwords
PASSWORD_HASHERS: list[str] = [
    "ronnie.core.passwords.hashers.PBKDF2PasswordHasher",
    "ronnie.core.passwords.hashers.ScryptPasswordHasher",
]
AUTH_PASSWORD_VALIDATORS: list[dict[str, object]] | None = None  # None → Django defaults

# Authentication
AUTH_USER_MODEL = "ronnie.contrib.auth.User"
AUTHENTICATION_BACKENDS: list[str] = ["ronnie.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "/accounts/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Cache framework (django.core.cache parity)
CACHES: dict[str, dict[str, object]] = {
    "default": {
        "BACKEND": "ronnie.cache.backends.locmem.LocMemCache",
        "LOCATION": "ronnie",
    }
}
CACHE_MIDDLEWARE_ALIAS = "default"
CACHE_MIDDLEWARE_SECONDS = 600
CACHE_MIDDLEWARE_KEY_PREFIX = ""

# Messages (flash): storage path, minimum level and level→tag overrides
MESSAGE_STORAGE = "ronnie.contrib.messages.storage.FallbackStorage"
MESSAGE_LEVEL = 20  # INFO; lower-level messages are dropped
MESSAGE_TAGS: dict[int, str] = {}

# Tasks
TASKS_BROKER = "ronnie.tasks.brokers.inline.InlineBroker"
TASKS_BROKER_URL: str | None = None  # redis://… when using RedisBroker
TASKS_RESULT_BACKEND = "cache:default"
TASKS_DEFAULT_QUEUE = "default"
TASKS_MAX_RETRIES = 0
TASKS_RETRY_BACKOFF = True
TASKS_SCHEDULE: dict[str, dict[str, object]] = {}

# Humanize
HUMANIZE_LANGUAGE = "es"  # "es" | "en"

# Admin
ADMIN_URL = "/admin"
ADMIN_SITE_HEADER = "Ronnie Administration"

# Sessions: "cookie" (signed, zero setup) | "db" | "cache" | dotted custom path
SESSION_ENGINE = "cookie"
SESSION_CACHE_ALIAS = "default"  # for SESSION_ENGINE="cache"

# Sessions
SESSION_COOKIE_NAME = "ronnie_session"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2  # two weeks, in seconds
SESSION_COOKIE_SAMESITE = "lax"
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_DOMAIN: str | None = None
