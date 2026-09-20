"""Initial schema."""

from ronnie.migrations import CreateTable, MigrationBase


class Migration(MigrationBase):
    dependencies = []

    operations = [
        CreateTable(
            name="user",
            pk="id",
            fields={
                "id": ("int | None", None),
                "username": ("str", ""),
                "email": ("str", ""),
                "password": ("str", ""),
                "first_name": ("str", ""),
                "last_name": ("str", ""),
                "is_active": ("bool", True),
                "is_staff": ("bool", False),
                "is_superuser": ("bool", False),
                "date_joined": ("str", "2026-09-20T09:47:16.489188+00:00"),
                "user_permissions": ("str", ""),
            },
            owner="auth",
        ),
    ]
