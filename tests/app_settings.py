"""Sample settings used by the testing-framework dogfood tests."""

SECRET_KEY = "app-settings-key"
DEBUG = False
INSTALLED_APPS = ["apps.pages", "apps.shop"]
MIDDLEWARE: list[str] = []
