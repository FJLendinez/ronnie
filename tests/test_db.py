"""Tests for DATABASES wiring and the migrate command (Fase 4)."""

from __future__ import annotations

import sqlite3
from io import StringIO

from ronnie.conf import settings
from ronnie.core.management import call_command
from ronnie.db import get_database


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
    def test_makemigrations_and_migrate_flow(self, tmp_path, monkeypatch):

        (tmp_path / "inv").mkdir()
        (tmp_path / "inv" / "__init__.py").write_text("")
        (tmp_path / "inv" / "models.py").write_text(
            "from dataclasses import dataclass\n\n\n"
            "@dataclass\nclass Widget:\n"
            "    id: int | None = None\n"
            '    label: str = ""\n\n\n'
            "TABLES: list[type] = [Widget]\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        settings.configure(
            SECRET_KEY="k",
            INSTALLED_APPS=["inv"],
            MIDDLEWARE=[],
            DATABASES={"default": {"ENGINE": "sqlite", "NAME": tmp_path / "w.db"}},
        )
        import ronnie
        from ronnie.apps import apps

        apps.clear_data()
        ronnie.setup()

        out = StringIO()
        call_command("makemigrations", stdout=out)
        assert (tmp_path / "inv" / "migrations" / "0001_initial.py").is_file()

        call_command("migrate", stdout=out)
        con = sqlite3.connect(str(tmp_path / "w.db"))
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert "widget" in tables and "ronnie_migration" in tables
        recorded = list(con.execute("SELECT app, name FROM ronnie_migration"))
        assert ("inv", "0001_initial") in [(str(a), str(b)) for a, b in recorded]
