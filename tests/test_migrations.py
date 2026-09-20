"""Tests for the real migration framework (files + recorded history)."""

from __future__ import annotations

import sqlite3
from io import StringIO
from pathlib import Path

import pytest

from ronnie.conf import settings
from ronnie.core.exceptions import CommandError
from ronnie.core.management import call_command
from ronnie.db import reset_databases_cache

MODELS_V1 = """from dataclasses import dataclass


@dataclass
class Widget:
    id: int | None = None
    label: str = ""
    price: float = 0.0


TABLES: list[type] = [Widget]
"""

MODELS_V2 = """from dataclasses import dataclass


@dataclass
class Widget:
    id: int | None = None
    label: str = ""
    price: float = 0.0
    stock: int = 0


TABLES: list[type] = [Widget]
"""

MODELS_V3 = """from dataclasses import dataclass


@dataclass
class Widget:
    id: int | None = None
    label: str = ""
    stock: int = 0


TABLES: list[type] = [Widget]
"""


def _purge_inv() -> None:
    import sys

    for module_name in [
        m
        for m in sys.modules
        if m == "inv" or m == "inv.models" or m == "inv.migrations" or m.startswith("inv.migrations.")
    ]:
        del sys.modules[module_name]


@pytest.fixture()
def app_env(tmp_path: Path, monkeypatch):
    """A throwaway app + database, importable via tmp sys.path."""
    _purge_inv()  # previous tests may have cached this package name
    (tmp_path / "inv").mkdir()
    (tmp_path / "inv" / "__init__.py").write_text("")
    (tmp_path / "inv" / "models.py").write_text(MODELS_V1)
    (tmp_path / "inv" / "migrations").mkdir()
    (tmp_path / "inv" / "migrations" / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    settings.configure(
        SECRET_KEY="mig",
        INSTALLED_APPS=["inv"],
        MIDDLEWARE=[],
        DATABASES={"default": {"ENGINE": "sqlite", "NAME": tmp_path / "mig.db"}},
    )
    import ronnie
    from ronnie.apps import apps

    apps.clear_data()
    ronnie.setup()
    yield tmp_path
    _purge_inv()
    reset_databases_cache()


def write_models(app_dir: Path, content: str) -> None:
    """Rewrite models.py and force a fresh import (drop module + registry)."""

    (app_dir / "inv" / "models.py").write_text(content)
    _purge_inv()
    from ronnie.apps import apps as registry

    registry.clear_data()
    import ronnie

    ronnie.setup()


def out() -> StringIO:
    return StringIO()


def sql(app_dir: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(app_dir / "mig.db"))


class TestMigrations:
    def test_makemigrations_writes_initial_file(self, app_env):
        call_command("makemigrations", stdout=out())
        file = app_env / "inv" / "migrations" / "0001_initial.py"
        assert file.is_file()
        content = file.read_text()
        assert "CreateTable" in content and '"widget"' in content
        assert "pk='id'" in content

    def test_migrate_creates_table_and_records_history(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        con = sql(app_env)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert "widget" in tables
        rows = [(str(a), str(b)) for a, b in con.execute("SELECT app, name FROM ronnie_migration")]
        assert rows == [("inv", "0001_initial")]

    def test_second_migrate_is_a_noop(self, app_env):
        call_command("makemigrations", stdout=out())
        buffer = out()
        call_command("migrate", stdout=buffer)
        call_command("migrate", stdout=buffer)
        assert "No migrations to apply" in buffer.getvalue()

    def test_showmigrations_applied_and_pending(self, app_env):
        call_command("makemigrations", stdout=out())
        buffer = out()
        call_command("showmigrations", stdout=buffer)
        assert "[ ] 0001_initial" in buffer.getvalue()
        call_command("migrate", stdout=out())
        buffer2 = out()
        call_command("showmigrations", stdout=buffer2)
        assert "[X] 0001_initial" in buffer2.getvalue()

    def test_sqlmigrate_prints_ddl(self, app_env):
        call_command("makemigrations", stdout=out())
        buffer = out()
        call_command("sqlmigrate", "inv", "0001", stdout=buffer)
        text = buffer.getvalue()
        assert "CREATE TABLE [widget]" in text

    def test_add_field_detects_applies_and_preserves_data(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        con = sql(app_env)
        con.execute("INSERT INTO widget (label, price) VALUES ('mug', 5.0)")
        con.commit()
        con.close()

        write_models(app_env, MODELS_V2)
        buffer = out()
        call_command("makemigrations", stdout=buffer)
        assert "Add field stock to widget" in buffer.getvalue()
        (app_env / "inv" / "migrations" / "0002_add_stock.py").exists()

        call_command("migrate", stdout=out())
        con = sql(app_env)
        assert list(con.execute("SELECT label, price, stock FROM widget")) == [("mug", 5.0, 0)]
        history = [(str(a), str(b)) for a, b in con.execute("SELECT app, name FROM ronnie_migration")]
        assert ("inv", "0002_add_stock") in history

    def test_remove_field(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        write_models(app_env, MODELS_V3)
        buffer = out()
        call_command("makemigrations", stdout=buffer)
        assert "Remove field price from widget" in buffer.getvalue()
        call_command("migrate", stdout=out())
        con = sql(app_env)
        columns = [r[1] for r in con.execute("PRAGMA table_info(widget)")]
        assert "price" not in columns and "stock" in columns

    def test_alter_field_rebuild_preserving_rows(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        write_models(app_env, MODELS_V2)  # add stock: int
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        con = sql(app_env)
        con.execute("INSERT INTO widget (label, price, stock) VALUES ('mug', 5.0, 3)")
        con.commit()
        con.close()

        altered = MODELS_V2.replace("stock: int = 0", "stock: str = 'x'")
        write_models(app_env, altered)  # alter stock: int → str
        buffer = out()
        call_command("makemigrations", stdout=buffer)
        assert "Alter field stock" in buffer.getvalue()
        call_command("migrate", stdout=out())
        con = sql(app_env)
        assert con.execute("SELECT count(*) FROM widget").fetchone()[0] == 1
        columns = [r[1] for r in con.execute("PRAGMA table_info(widget)")]
        assert "stock" in columns  # rebuilt table keeps the column

    def test_rollback_zero_reverses_and_unrecords(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        write_models(app_env, MODELS_V2)
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())

        buffer = out()
        call_command("migrate", "inv", "zero", stdout=buffer)
        assert "Unapplying inv.0002_add_stock" in buffer.getvalue()
        assert "Unapplying inv.0001_initial" in buffer.getvalue()
        con = sql(app_env)
        assert not list(con.execute("SELECT name FROM sqlite_master WHERE name='widget'"))
        assert not list(con.execute("SELECT * FROM ronnie_migration"))

    def test_rollback_to_specific_migration(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        write_models(app_env, MODELS_V2)
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        buffer = out()
        call_command("migrate", "inv", "0001", stdout=buffer)
        assert "Unapplying inv.0002_add_stock" in buffer.getvalue()
        con = sql(app_env)
        columns = [r[1] for r in con.execute("PRAGMA table_info(widget)")]
        assert "stock" not in columns
        history = [(str(b)) for _a, b in con.execute("SELECT app, name FROM ronnie_migration")]
        assert history == ["0001_initial"]

    def test_migrate_forward_to_specific_migration(self, app_env):
        write_models(app_env, MODELS_V2)
        call_command("makemigrations", stdout=out())  # 0001 + 0002 in one go? no: initial only
        # generate both: makemigrations made 0001 with all fields; instead step by step
        call_command("migrate", "inv", "0001", stdout=out())
        con = sql(app_env)
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE name='widget'").fetchone()[0] == 1

    def test_fake_records_without_running(self, app_env):
        call_command("makemigrations", stdout=out())
        buffer = out()
        call_command("migrate", "--fake", stdout=buffer)
        assert "Faking inv.0001_initial" in buffer.getvalue()
        con = sql(app_env)
        assert not list(con.execute("SELECT name FROM sqlite_master WHERE name='widget'"))
        assert list(con.execute("SELECT name FROM ronnie_migration"))

    def test_fake_initial_over_existing_tables(self, app_env):
        from ronnie.db import install_tables

        install_tables()  # legacy transform path created the table already
        call_command("makemigrations", stdout=out())
        buffer = out()
        call_command("migrate", "--fake-initial", stdout=buffer)
        con = sql(app_env)
        assert list(con.execute("SELECT name FROM ronnie_migration"))

    def test_dry_run_prints_sql_and_executes_nothing(self, app_env):
        call_command("makemigrations", stdout=out())
        buffer = out()
        call_command("migrate", "--dry-run", stdout=buffer)
        text = buffer.getvalue()
        assert "CREATE TABLE [widget]" in text
        con = sql(app_env)
        assert not list(con.execute("SELECT name FROM sqlite_master WHERE name='widget'"))
        assert not list(con.execute("SELECT name FROM ronnie_migration WHERE app='inv'"))

    def test_makemigrations_check_exit_code(self, app_env):
        with pytest.raises(CommandError, match="require migrations"):
            call_command("makemigrations", "--check", stdout=out())
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        buffer = out()
        call_command("makemigrations", "--check", stdout=buffer)  # clean → no error
        assert "No changes detected" in buffer.getvalue()

    def test_makemigrations_dry_run_writes_nothing(self, app_env):
        buffer = out()
        call_command("makemigrations", "--dry-run", stdout=buffer)
        assert "Would create" in buffer.getvalue()
        assert not (app_env / "inv" / "migrations" / "0001_initial.py").exists()

    def test_empty_migration_and_handwritten_ops(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        buffer = out()
        call_command("makemigrations", "--empty", "--name", "backfill", stdout=buffer)
        empty = app_env / "inv" / "migrations" / "0002_backfill.py"
        assert empty.is_file()
        # hand-write a RunSQL migration
        empty.write_text("""
from ronnie.migrations import MigrationBase, RunSQL

class Migration(MigrationBase):
    dependencies = [("inv", "0001_initial")]
    operations = [
        RunSQL("CREATE TABLE [inv_note] ([id] INTEGER PRIMARY KEY, [text] TEXT);",
               reverse_sql="DROP TABLE [inv_note];"),
    ]
""")
        call_command("migrate", stdout=out())
        con = sql(app_env)
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE name='inv_note'").fetchone()[0]
        call_command("migrate", "inv", "0001", stdout=out())  # rolls back RunSQL reverse
        con = sql(app_env)
        assert not con.execute("SELECT count(*) FROM sqlite_master WHERE name='inv_note'").fetchone()[0]

    def test_runpython_data_migration(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        (app_env / "inv" / "migrations" / "0002_seed.py").write_text("""
from ronnie.migrations import MigrationBase, RunPython

def seed(db):
    db.execute("INSERT INTO widget (label, price) VALUES ('seeded', 1.0)")

def unseed(db):
    db.execute("DELETE FROM widget WHERE label = 'seeded'")

class Migration(MigrationBase):
    dependencies = [("inv", "0001_initial")]
    operations = [RunPython(seed, reverse_code=unseed)]
""")
        call_command("migrate", stdout=out())
        con = sql(app_env)
        assert con.execute("SELECT count(*) FROM widget WHERE label='seeded'").fetchone()[0] == 1
        call_command("migrate", "inv", "0001", stdout=out())
        con = sql(app_env)
        assert con.execute("SELECT count(*) FROM widget WHERE label='seeded'").fetchone()[0] == 0

    def test_irreversible_migration_rejected_on_rollback(self, app_env):
        call_command("makemigrations", stdout=out())
        call_command("migrate", stdout=out())
        (app_env / "inv" / "migrations" / "0002_fire.py").write_text("""
from ronnie.migrations import MigrationBase, RunSQL

class Migration(MigrationBase):
    dependencies = [("inv", "0001_initial")]
    operations = [RunSQL("CREATE TABLE [x] ([id] INTEGER);")]
""")
        call_command("migrate", stdout=out())
        with pytest.raises(CommandError, match="not reversible"):
            call_command("migrate", "inv", "zero", stdout=out())

    def test_no_migrations_hint(self, tmp_path: Path, monkeypatch):
        (tmp_path / "bare").mkdir()
        (tmp_path / "bare" / "__init__.py").write_text("")
        monkeypatch.syspath_prepend(str(tmp_path))
        settings.configure(
            SECRET_KEY="k",
            INSTALLED_APPS=["bare"],
            MIDDLEWARE=[],
            DATABASES={"default": {"ENGINE": "sqlite", "NAME": tmp_path / "b.db"}},
        )
        import ronnie
        from ronnie.apps import apps

        apps.clear_data()
        ronnie.setup()
        buffer = StringIO()
        call_command("migrate", stdout=buffer)
        assert "No migrations found" in buffer.getvalue()
        assert "makemigrations" in buffer.getvalue()

    def test_unknown_app_and_migration_errors(self, app_env):
        with pytest.raises(LookupError):
            call_command("makemigrations", "nope", stdout=out())
        with pytest.raises(CommandError, match="Cannot find migration"):
            call_command("sqlmigrate", "inv", "9999", stdout=out())


class TestContribMigrations:
    def test_contrib_apps_ship_initial_migrations(self):
        from ronnie.apps import apps as registry
        from ronnie.migrations.loader import MigrationLoader

        settings.configure(
            SECRET_KEY="k",
            INSTALLED_APPS=["ronnie.contrib.sessions", "ronnie.contrib.auth", "ronnie.contrib.redirects"],
            MIDDLEWARE=[],
            DATABASES={"default": {"ENGINE": "sqlite", "NAME": ":memory:"}},
        )
        import ronnie

        registry.clear_data()
        ronnie.setup()
        loader = MigrationLoader()
        apps_with_migrations = {app for (app, _name) in loader.nodes}
        assert {"sessions", "auth", "redirects"} <= apps_with_migrations
