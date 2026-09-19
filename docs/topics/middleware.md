# Middleware

Middleware wraps every request/response cycle: security headers, sessions,
CSRF, authentication, messages. Ronnie's stack is a plain list of dotted
paths in settings, so you can see — and change — the whole pipeline.

## The MIDDLEWARE setting

```python
MIDDLEWARE = [
    "ronnie.middleware.security.SecurityMiddleware",
    "ronnie.middleware.host.HostValidationMiddleware",
    "ronnie.contrib.sessions.middleware.SessionMiddleware",
    "ronnie.middleware.csrf.CsrfMiddleware",
    "ronnie.contrib.auth.middleware.AuthMiddleware",
    "ronnie.contrib.messages.middleware.MessagesMiddleware",
    "ronnie.middleware.clickjacking.XFrameOptionsMiddleware",
    "ronnie.contrib.redirects.middleware.RedirectFallbackMiddleware",
]
```

The list above is the recommended stack (a fresh `startproject` ships it).

- **Order is top-to-bottom on the request** and bottom-to-top on the
  response: the first entry is the outermost wrapper.
- Entries are dotted paths resolved at app-build time — a typo fails
  immediately with `ImproperlyConfigured`.
- A session middleware is required; if none is listed, Ronnie appends the
  default one innermost so CSRF/auth/messages keep working.

## Writing middleware

A middleware is any callable taking `(app)` and returning an async ASGI
callable. Pure ASGI keeps overhead at zero:

```python
class XRequestIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":          # pass websockets/lifespan through
            await self.app(scope, receive, send)
            return

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", b"…"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)
```

Register it by path:

```python
MIDDLEWARE = [..., "myproject.middleware.XRequestIDMiddleware"]
```

### Communicating with handlers

Mutate the **scope**, never globals. Handlers read scope values through
FastHTML's special parameters:

| Scope key | Handler parameter | Set by |
|---|---|---|
| `session` | `sess` | SessionMiddleware |
| `user` / `auth` | `auth` | AuthMiddleware |

## The built-in stack

| Middleware | Responsibility | Key settings |
|---|---|---|
| `SecurityMiddleware` | HSTS, SSL redirect, `Referrer-Policy`, COOP, `X-Content-Type-Options` | `SECURE_*` |
| `HostValidationMiddleware` | Reject spoofed `Host` headers (400) | `ALLOWED_HOSTS`, `USE_X_FORWARDED_HOST` |
| `SessionMiddleware` | Loads/saves `scope["session"]` per engine | `SESSION_*` |
| `CsrfMiddleware` | Validates tokens on unsafe methods | `CSRF_*` |
| `AuthMiddleware` | Attaches `user` (or anonymous) to the scope | — |
| `MessagesMiddleware` | Ships cookie-stored flash messages | `MESSAGE_STORAGE` |
| `XFrameOptionsMiddleware` | `X-Frame-Options: DENY` | `X_FRAME_OPTIONS` |
| `RedirectFallbackMiddleware` | DB redirects on 404 | — |

Details for each live in their topic pages
([security](security.md), [sessions](sessions.md),
[authentication](authentication.md), [messages](messages.md),
[redirects](redirects.md)).

## Testing middleware

Swap the stack per test with
[`modify_settings`](testing.md#overriding-settings):

```python
from ronnie.testing.utils import modify_settings

with modify_settings(MIDDLEWARE={"append": ["myproject.middleware.XRequestIDMiddleware"]}):
    response = client.get("/")
```
