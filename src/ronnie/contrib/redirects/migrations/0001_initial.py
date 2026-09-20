"""Initial schema."""

from ronnie.migrations import CreateTable, MigrationBase


class Migration(MigrationBase):
    dependencies = []

    operations = [
        CreateTable(
            name="ronnieredirect",
            pk="old_path",
            fields={"old_path": ("str", None), "new_path": ("str", ""), "response_code": ("int", 302)},
            owner="redirects",
        ),
    ]
