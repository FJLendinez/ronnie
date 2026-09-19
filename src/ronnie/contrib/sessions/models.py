"""Database model for db-backed sessions."""

from dataclasses import dataclass


@dataclass
class RonnieSession:
    """A stored session (db engine). ``data`` is a JSON-encoded dict."""

    pk_name = "session_key"  # get_table() convention for non-`id` primary keys

    session_key: str  # primary key (32 hex chars)
    data: str = "{}"
    expire_date: str = ""  # ISO-8601 UTC


TABLES: list[type] = [RonnieSession]
