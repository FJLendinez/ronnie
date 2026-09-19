"""Tests for DATABASES wiring and the migrate command (Fase 4)."""

from __future__ import annotations

import sqlite3
from io import StringIO

from ronnie.conf import settings
from ronnie.core.management import call_command
from ronnie.db import get_database, install_tables


def configure_with_db(tmp_path):
    settings.configure(
        SECRET_KEY="k",
        INSTALLED_APPS=["apps.shop"],
        MIDDLEWARE=[],
        DATABASES={"default": {"ENGINE": "sqlite", "NAME": tmp_path / "test.sqlite3"}},
    )
    return str(tmp_path / "test.sqlite3")


class TestGetDatabase:
    def test_sqlite_connection_created(self, tmp_path):
        path = configure_with_db(tmp_path)
        db = get_database()
        assert db is not None
        assert sqlite3.connect(path)  # valid file db

    def test_unknown_engine_rejected(self, tmp_path):
        settings.configure(
            SECRET_KEY="k",
            DATABASES={"default": {"ENGINE": "oracle", "NAME": "x"}},
        )
        import pytest

        from ronnie.core.exceptions import ImproperlyConfigured

        with pytest.raises(ImproperlyConfigured, match="Unknown database ENGINE"):
            get_database()

    def test_missing_name_rejected(self):
        settings.configure(SECRET_KEY="k", DATABASES={"default": {"ENGINE": "sqlite"}})
        import pytest

        from ronnie.core.exceptions import ImproperlyConfigured

        with pytest.raises(ImproperlyConfigured, match="NAME is required"):
            get_database()

    def test_missing_alias_rejected(self):
        settings.configure(SECRET_KEY="k", DATABASES={})
        import pytest

        from ronnie.core.exceptions import ImproperlyConfigured

        with pytest.raises(ImproperlyConfigured, match="no 'default' alias"):
            get_database()


class TestMigrate:
    def test_creates_tables(self, tmp_path):
        path = configure_with_db(tmp_path)
        out = StringIO()
        call_command("migrate", stdout=out)
        assert "shop.Product" in out.getvalue()
        con = sqlite3.connect(path)
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert any("product" in name.lower() for name in tables)

    def test_install_tables_transform(self, tmp_path):
        configure_with_db(tmp_path)
        created = install_tables()
        assert created == ["shop.Product"]
        # Second run is idempotent (transform=True handles drift).
        assert install_tables() == ["shop.Product"]
