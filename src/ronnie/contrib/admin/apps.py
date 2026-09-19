"""AppConfig for contrib.admin: mounts routes and autodiscovers admin.py."""

from __future__ import annotations

from ...apps import AppConfig


class AdminConfig(AppConfig):
    name = "ronnie.contrib.admin"
    verbose_name = "Admin"

    def ready(self) -> None:
        from . import views  # noqa: F401 - registers the /admin routes

        self.autodiscover()

    @staticmethod
    def autodiscover() -> None:
        """Import every installed app's ``admin.py`` (Django's autodiscover)."""
        from ...apps import apps

        for config in apps.get_app_configs():
            if config.name.startswith("ronnie.contrib.admin"):
                continue
            try:
                __import__(f"{config.name}.admin")
            except ImportError as exc:
                if getattr(exc, "name", None) != f"{config.name}.admin":
                    raise  # broken admin.py: fail loudly
