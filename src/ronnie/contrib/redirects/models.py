"""Redirect table (Django's Redirect model minus the sites framework)."""

from dataclasses import dataclass


@dataclass
class RonnieRedirect:
    pk_name = "old_path"

    old_path: str  # unique; e.g. "/old-url/"
    new_path: str = ""  # empty → 410 Gone
    response_code: int = 302  # 301 for permanent


TABLES: list[type] = [RonnieRedirect]
