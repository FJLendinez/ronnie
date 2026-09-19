"""Create a superuser account (interactive, or --noinput via env vars)."""

from __future__ import annotations

import argparse
import getpass
import os
from typing import Any

from ronnie.core.exceptions import CommandError, ValidationError
from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Create a superuser account."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--username")
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--noinput", action="store_true", help="Read credentials from RONNIE_SUPERUSER_* env vars."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.contrib.auth.models import create_superuser, get_user_by_username
        from ronnie.core.passwords import validate_password

        username = options.get("username")
        email = options.get("email") or ""
        if options.get("noinput"):
            username = username or os.environ.get("RONNIE_SUPERUSER_USERNAME", "")
            password = os.environ.get("RONNIE_SUPERUSER_PASSWORD", "")
            email = email or os.environ.get("RONNIE_SUPERUSER_EMAIL", "")
            if not username or not password:
                raise CommandError(
                    "--noinput requires RONNIE_SUPERUSER_USERNAME and RONNIE_SUPERUSER_PASSWORD."
                )
        else:
            username = username or input("Username: ").strip()
            email = email or input("Email (optional): ").strip()
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("Passwords didn't match.")

        if not username:
            raise CommandError("Username is required.")
        if get_user_by_username(username) is not None:
            raise CommandError(f"Username {username!r} is already taken.")
        try:
            validate_password(password)
        except ValidationError as err:
            raise CommandError("; ".join(err.messages)) from err

        user = create_superuser(username, password, email=email)
        self.stdout.write(self.style.SUCCESS(f"Superuser {username!r} created (id={user.id})."))
