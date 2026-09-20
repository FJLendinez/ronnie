"""Initial schema."""

from ronnie.migrations import CreateTable, MigrationBase


class Migration(MigrationBase):
    dependencies = []

    operations = [
        CreateTable(
            name="ronniesession",
            pk="session_key",
            fields={"session_key": ("str", None), "data": ("str", "{}"), "expire_date": ("str", "")},
            owner="sessions",
        ),
    ]
