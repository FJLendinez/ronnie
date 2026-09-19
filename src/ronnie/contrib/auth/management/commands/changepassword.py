"""Change a user's password (interactive)."""

from __future__ import annotations

import argparse
import getpass
from typing import Any

from ronnie.core.exceptions import CommandError, ValidationError
from ronnie.core.management import BaseCommand


class Command(BaseCommand):
    help = "Change a user's password."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("username")

    def handle(self, *args: Any, **options: Any) -> None:
        from ronnie.contrib.auth.models import _user_table, get_user_by_username
        from ronnie.core.passwords import make_password, validate_password

        username = options["username"]
        user = get_user_by_username(username)
        if user is None:
            raise CommandError(f"User {username!r} not found.")

        password = getpass.getpass("New password: ")
        if password != getpass.getpass("New password (again): "):
            raise CommandError("Passwords didn't match.")
        try:
            validate_password(password, user=user)
        except ValidationError as err:
            raise CommandError("; ".join(err.messages)) from err

        user.password = make_password(password)
        _user_table().update(user)
        self.stdout.write(self.style.SUCCESS(f"Password changed for {username!r}."))
