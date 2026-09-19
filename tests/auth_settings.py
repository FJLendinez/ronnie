"""Settings for auth e2e tests."""

SECRET_KEY = "auth-test-key"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]
INSTALLED_APPS = ["apps.pages", "ronnie.contrib.sessions", "ronnie.contrib.auth"]
MIDDLEWARE: list[str] = [
    "ronnie.middleware.security.SecurityMiddleware",
    "ronnie.middleware.host.HostValidationMiddleware",
    "ronnie.contrib.sessions.middleware.SessionMiddleware",
    "ronnie.middleware.csrf.CsrfMiddleware",
    "ronnie.contrib.auth.middleware.AuthMiddleware",
    "ronnie.middleware.clickjacking.XFrameOptionsMiddleware",
]
