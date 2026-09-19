"""AppConfig for contrib.redirects."""

from __future__ import annotations

from ...apps import AppConfig


class RedirectsConfig(AppConfig):
    name = "ronnie.contrib.redirects"
    verbose_name = "Redirects"

    def ready(self) -> None:
        # Optional: manage redirects from the admin when both apps are installed.
        try:
            from ..admin import site
            from .models import RonnieRedirect

            if RonnieRedirect not in site.registry:
                site.register(RonnieRedirect, list_display=("old_path", "new_path", "response_code"))
        except Exception:
            pass
