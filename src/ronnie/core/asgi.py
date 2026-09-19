"""ASGI application factory — Ronnie's ``get_asgi_application()``.

Builds a FastHTML application from settings:

- middleware stack resolved from the ``MIDDLEWARE`` setting (dotted paths),
- exception handlers (custom 404/500 FT pages),
- session cookie wiring from ``SESSION_*`` settings,
- per-app routers mounted via autodiscovery (``<app>.routes`` / ``<app>.views``),
- static files mounted when ``STATIC_ROOT`` exists.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from fasthtml.common import H1, Code, Main, P, Titled
from fasthtml.core import FastHTML
from starlette.middleware import Middleware
from starlette.staticfiles import StaticFiles

from .. import __version__
from ..apps import apps
from ..core.exceptions import ImproperlyConfigured
from ..core.logging import configure_logging
from ..core.routing import mount_routers

__all__ = ["get_asgi_application", "resolve_middleware"]

EPHEMERAL_KEY = "ronnie-insecure-ephemeral-key"

_server_error_logged = False


def resolve_middleware(dotted_paths: list[str]) -> list[Middleware]:
    """Turn ``MIDDLEWARE`` dotted paths into Starlette ``Middleware`` objects."""
    middlewares = []
    for path in dotted_paths:
        module_path, _, attr = path.rpartition(".")
        if not module_path:
            raise ImproperlyConfigured(f"MIDDLEWARE entries must be dotted paths: {path!r}")
        try:
            cls = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError) as exc:
            raise ImproperlyConfigured(f"Cannot import middleware {path!r}: {exc}") from exc
        middlewares.append(Middleware(cls))
    return middlewares


def _not_found(req: Any, exc: Exception) -> Any:
    return Titled(
        "404",
        Main(H1("Page not found"), P("The requested URL was not found:"), Code(str(req.url.path))),
    )


def _server_error(req: Any, exc: Exception) -> Any:
    # Plain Starlette response: FastHTML's FT wrapping of an Exception-keyed
    # handler would pass the exception class as status_code.
    from starlette.responses import HTMLResponse

    return HTMLResponse(
        "<!doctype html><html><head><title>500</title></head>"
        "<body><h1>Server error</h1><p>Something went wrong.</p></body></html>",
        status_code=500,
    )


def _mount_static(app: FastHTML, settings: Any) -> None:
    static_root = getattr(settings, "STATIC_ROOT", None)
    if not static_root:
        return
    directory = Path(static_root)
    if not directory.is_dir():
        return
    app.mount(str(settings.STATIC_URL).rstrip("/") or "/", StaticFiles(directory=directory), name="static")


def get_asgi_application() -> FastHTML:
    """Build (and boot) the Ronnie ASGI application from settings."""
    import ronnie

    ronnie.setup()  # idempotent: settings + app registry + logging
    from ..conf import settings

    configure_logging()

    secret_key = settings.SECRET_KEY or EPHEMERAL_KEY
    if not settings.SECRET_KEY and settings.DEBUG:
        import logging

        logging.getLogger("ronnie").warning(
            "SECRET_KEY is empty; using an ephemeral key (sessions break on restart)."
        )

    exception_handlers: dict[Any, Any] = {404: _not_found}
    if not settings.DEBUG:
        exception_handlers[Exception] = _server_error

    middleware = resolve_middleware(list(settings.MIDDLEWARE))
    # Ronnie owns the session middleware placement (innermost) so CSRF/auth
    # middlewares listed after it in MIDDLEWARE can read scope["session"].
    from ..middleware.session import SessionMiddleware, is_session_middleware

    if not any(is_session_middleware(m) for m in middleware):
        middleware.append(Middleware(SessionMiddleware))

    app = FastHTML(
        debug=settings.DEBUG,
        middleware=middleware,
        exception_handlers=exception_handlers,
        secret_key=secret_key,
        sess_cls=None,  # sessions handled inside Ronnie's MIDDLEWARE stack
        title=f"Ronnie {__version__}",
    )

    mount_routers(app, apps)
    _mount_static(app, settings)
    return app
