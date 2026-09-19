"""AppConfig for contrib.auth."""

from __future__ import annotations

from ...apps import AppConfig


class AuthConfig(AppConfig):
    name = "ronnie.contrib.auth"
    verbose_name = "Authentication"

    def ready(self) -> None:
        # Mount the built-in /accounts routes by importing the views module.
        from . import views  # noqa: F401
