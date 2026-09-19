"""Backward-compatible alias: the session middleware lives in contrib.sessions."""

from ..contrib.sessions.middleware import SessionMiddleware, is_session_middleware

__all__ = ["SessionMiddleware", "is_session_middleware"]
