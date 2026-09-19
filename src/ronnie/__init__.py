"""Ronnie: Django-style framework layer on top of FastHTML.

Usage::

    import ronnie
    ronnie.setup()          # or set RONNIE_SETTINGS_MODULE first

See PLAN.md for the full architecture.
"""

__version__ = "0.1.0.dev0"

__all__ = ["__version__", "setup"]


def setup(settings_module: str | None = None) -> None:
    """Configure settings and populate the app registry.

    Equivalent of ``django.setup()``. Safe to call multiple times: once the
    registry is ready, subsequent calls are no-ops. System checks are *not*
    run here; they run when commands execute (``ronnie check`` et al.),
    exactly like Django.

    Resolution order for the settings module:
    1. the ``settings_module`` argument,
    2. the ``RONNIE_SETTINGS_MODULE`` environment variable.
    """
    from . import conf
    from .apps import apps

    if not conf.settings.configured:
        conf.settings._setup(settings_module)
    apps.populate(conf.settings.INSTALLED_APPS)
