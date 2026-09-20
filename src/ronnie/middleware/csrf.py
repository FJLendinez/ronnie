"""CSRF protection — ``CsrfViewMiddleware`` equivalent for FastHTML.

Flow (Django semantics):

- The per-session secret lives in ``session["_csrf_token"]`` (created lazily).
- Safe methods pass through. Unsafe methods (POST/PUT/PATCH/DELETE) must
  present the token either as the ``csrfmiddlewaretoken`` form field or the
  ``X-CSRFToken`` header (the natural fit for HTMX requests).
- On HTTPS, ``Origin`` (or ``Referer``) must be same-origin (or listed in
  ``CSRF_TRUSTED_ORIGINS``).
- Exemptions: ``CSRF_EXEMPT_PATHS`` regexes.

Helpers::

    from ronnie.middleware.csrf import csrf_token, CsrfToken

    def my_form(req):
        return Form(CsrfToken(req), Input(name="title"), hx_post=save)

The request body is drained and replayed (once for the middleware, once for
the app) so form parsing still works downstream.
"""

from __future__ import annotations

import hmac
import re
import secrets
from typing import Any
from urllib.parse import urlsplit

from ..common import Hidden
from ..core.exceptions import ImproperlyConfigured

__all__ = ["TOKEN_SESSION_KEY", "CsrfMiddleware", "CsrfToken", "csrf_token", "hx_csrf_headers"]

TOKEN_SESSION_KEY = "_csrf_token"
FORM_FIELD = "csrfmiddlewaretoken"
HEADER_NAME = "x-csrftoken"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY_BYTES = 2_621_440  # DATA_UPLOAD_MAX_MEMORY_SIZE parity (2.5 MB)


def _session_of(request_or_session: Any) -> dict[str, Any]:
    """Extract the mutable session dict from a Request, or accept it directly."""
    if isinstance(request_or_session, dict):
        return request_or_session
    scope = getattr(request_or_session, "scope", None)
    session = scope.get("session") if isinstance(scope, dict) else None
    if not isinstance(session, dict):  # pragma: no cover - defensive
        raise ImproperlyConfigured(
            "CSRF requires the session middleware (pass `req` or `sess` to csrf_token)."
        )
    return session


def csrf_token(request_or_session: Any) -> str:
    """Return (creating if needed) the CSRF token for a request or session dict."""
    session = _session_of(request_or_session)
    token = session.get(TOKEN_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[TOKEN_SESSION_KEY] = token
    return token


def CsrfToken(request_or_session: Any) -> Any:
    """Hidden input carrying the CSRF token for forms."""
    token: str = csrf_token(request_or_session)
    return Hidden(name=FORM_FIELD, value=token)  # type: ignore[misc]


def hx_csrf_headers(token: str) -> dict[str, str]:
    """Headers dict for HTMX's ``hx-headers`` attribute."""
    return {"X-CSRFToken": token}


# Route patterns collected at app-build time from handlers decorated with
# @csrf_exempt (path parameters become [^/]+ segments).
_exempt_route_patterns: list[re.Pattern[str]] = []


def register_exempt_route(path: str) -> None:
    """Register a route path as CSRF-exempt (called during route mounting)."""
    if not path.startswith("/"):
        path = "/" + path  # routers may store unprefixed paths
    pattern = re.sub(r"\{[^}]+\}", "[^/]+", path)
    _exempt_route_patterns.append(re.compile(f"^{pattern}$"))


def reset_exempts() -> None:
    """Test helper: forget decorator-based exemptions."""
    _exempt_route_patterns.clear()


def csrf_exempt(view: Any) -> Any:
    """Mark a handler as exempt from CSRF checking (like a view decorator).

    Usable bare or with arguments; the route path it gets mounted under is
    collected automatically when the application is built.
    """
    view._ronnie_csrf_exempt = True
    return view


class CsrfMiddleware:
    """Reject unsafe requests without a valid CSRF token (403)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        from ..conf import settings

        if self._exempt(scope.get("path", "/")):
            await self.app(scope, receive, send)
            return

        session = scope.get("session")
        if session is None:
            # Session middleware missing or misordered: fail closed.
            await self._reject(scope, receive, send, "CSRF checking requires session middleware.")
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        body = await self._drain(receive)

        submitted = headers.get(HEADER_NAME) or self._form_token(scope, headers, body)
        expected = session.get(TOKEN_SESSION_KEY)

        reason = None
        same = hmac.compare_digest(str(submitted).encode("utf-8", "replace"), str(expected or "").encode())
        if not expected or not submitted or not same:
            reason = "CSRF token missing or incorrect."
        elif scope.get("scheme") == "https" and not self._origin_ok(scope, headers, settings):
            reason = "Origin/Referer checking failed — no Origin nor Referer matches the host."
        if reason:
            await self._reject(scope, receive, send, reason)
            return

        # ASGI signature is app(scope, receive, send): replay the drained body.
        await self.app(scope, self._replay_receive(body), send)

    # -- helpers -------------------------------------------------------------------

    def _exempt(self, path: str) -> bool:
        from ..conf import settings

        if any(pattern.fullmatch(path) for pattern in _exempt_route_patterns):
            return True  # decorator-based exemption (@csrf_exempt)
        return any(re.search(pattern, path) for pattern in getattr(settings, "CSRF_EXEMPT_PATHS", None) or [])

    @staticmethod
    async def _drain(receive: Any) -> bytes:
        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                if not message.get("more_body"):
                    break
                if len(body) > MAX_BODY_BYTES:
                    break
            elif message["type"] == "http.disconnect":
                break
        return body

    @staticmethod
    def _replay_receive(body: bytes) -> Any:
        state = {"sent": False}

        async def receive_once() -> dict[str, Any]:
            if not state["sent"]:
                state["sent"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        return receive_once

    @staticmethod
    def _form_token(scope: dict[str, Any], headers: dict[str, str], body: bytes) -> str | None:
        content_type = headers.get("content-type", "")
        if "form-urlencoded" in content_type:
            from urllib.parse import parse_qs

            values = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            if token := values.get(FORM_FIELD):
                return token[0]
        elif "multipart/form-data" in content_type and FORM_FIELD.encode() in body:
            # Cheap multipart extraction for the token part only.
            match = re.search(rf'name="{FORM_FIELD}"\r?\n\r?\n([^\r\n]+)\r?\n'.encode(), body)
            if match:
                return match.group(1).decode("utf-8", "replace")
        return None

    @staticmethod
    def _origin_ok(scope: dict[str, Any], headers: dict[str, str], settings: Any) -> bool:
        host = next((v.decode() for k, v in scope.get("headers", []) if k == b"host"), "")
        trusted = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", None) or [])
        origin = headers.get("origin")
        if origin:
            netloc = urlsplit(origin).netloc
            return netloc == host or origin.rstrip("/") in trusted or netloc in trusted
        referer = headers.get("referer")
        if referer:
            parts = urlsplit(referer)
            return parts.netloc == host and (parts.scheme == "https" or parts.scheme == scope.get("scheme"))
        return False  # https without Origin/Referer: reject (Django parity)

    @staticmethod
    async def _reject(scope: Any, receive: Any, send: Any, reason: str) -> None:
        from starlette.responses import HTMLResponse

        page = f"""<!doctype html><html><head><title>403 Forbidden</title></head>
<body><h1>CSRF verification failed. Request aborted.</h1>
<p>{reason}</p></body></html>"""
        await HTMLResponse(page, status_code=403)(scope, receive, send)
