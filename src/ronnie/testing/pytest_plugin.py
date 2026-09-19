"""pytest plugin: ``client`` and ``db`` fixtures for Ronnie projects."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from .client import RonnieTestClient
from .utils import override_settings

__all__ = ["client", "db", "ronnie_settings"]


@pytest.fixture
def client() -> RonnieTestClient:
    """A test client against the ASGI app built from current settings."""
    return RonnieTestClient()


@pytest.fixture
def ronnie_settings() -> type[override_settings]:
    """Context-manager factory to override settings inside a pytest test."""
    return override_settings


@pytest.fixture
def db() -> Iterator[None]:
    """A throwaway sqlite database with app tables installed, per test."""
    from ..db import install_tables, reset_databases_cache

    with TemporaryDirectory() as tmp:
        override = override_settings(
            DATABASES={"default": {"ENGINE": "sqlite", "NAME": Path(tmp) / "test.sqlite3"}}
        )
        override.enable()
        reset_databases_cache()
        try:
            install_tables()
            yield
        finally:
            override.disable()
            reset_databases_cache()
