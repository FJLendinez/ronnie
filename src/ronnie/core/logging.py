"""Logging configuration (Django-style LOGGING dict)."""

from __future__ import annotations

import logging.config
from typing import Any

__all__ = ["DEFAULT_LOGGING", "configure_logging"]

DEFAULT_LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {"format": "{asctime} {levelname:8} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "console"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


def configure_logging() -> None:
    """Apply ``settings.LOGGING`` if provided, else the default config."""
    from ..conf import settings

    config = settings.LOGGING if settings.LOGGING else DEFAULT_LOGGING
    logging.config.dictConfig(config)
