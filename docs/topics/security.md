# Security

Ronnie ships a hardened-by-default request pipeline: security headers, host
validation, CSRF, signing and password hashing. Most of it is configuration
you will touch once per project — this page tells you where.

## The quick audit

```bash
ronnie check --deploy
```

This extends the normal startup checks with deployment-only warnings: empty
`SECRET_KEY`, `DEBUG = True`, missing SSL redirect, HSTS disabled, cookies
without `Secure`. Wire it into CI or your release checklist.

## Secret key

`SECRET_KEY` signs sessions, flash-message cookies, password-reset tokens —
everything that must be tamper-proof. Generate one with:

```bash
ronnie generatesecretkey
```

Rules:

- Keep it out of version control (load it from the environment).
- Rotating it logs everyone out and invalidates signed values. During
  rotation, keep the old key in `SECRET_KEY_FALLBACKS` — old tokens still
  verify, new ones are signed with the primary key.

## Security headers

`SecurityMiddleware` (in the default stack) sets response headers unless
your app already provided them:

| Setting | Default | Header |
|---|---|---|
| `SECURE_HSTS_SECONDS` | `0` (off) | `Strict-Transport-Security: max-age=…` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | appends `includeSubDomains` |
| `SECURE_HSTS_PRELOAD` | `False` | appends `preload` |
| `SECURE_SSL_REDIRECT` | `False` | 301 `http→https` (honours `SECURE_PROXY_SSL_HEADER`) |
| `SECURE_SSL_HOST` | `None` | Target host for the redirect |
| `SECURE_REDIRECT_EXEMPT` | `[]` | Regexes of paths exempt from the redirect |
| `SECURE_REFERRER_POLICY` | `"same-origin"` | `Referrer-Policy` |
| `SECURE_CROSS_ORIGIN_OPENER_POLICY` | `"same-origin"` | `Cross-Origin-Opener-Policy` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | `X-Content-Type-Options: nosniff` |

Production example:

```python
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
```

When TLS terminates at a proxy, trust the forwarding header explicitly:

```python
SECURE_PROXY_SSL_HEADER = ("X-Forwarded-Proto", "https")  # only if your proxy sets it
```

## Host validation

`HostValidationMiddleware` rejects requests whose `Host` header is not
allowed — the classic defense against cache poisoning and
password-reset-link poisoning:

```python
ALLOWED_HOSTS = ["example.com", ".example.com"]   # ".example.com" covers subdomains
```

With `DEBUG = True` and an empty list, localhost variants (and the test
client's `testserver`) are allowed; in production every host must be
listed. `USE_X_FORWARDED_HOST = True` switches the check to
`X-Forwarded-Host` (only behind a trusted proxy).

## Clickjacking

`XFrameOptionsMiddleware` sends `X-Frame-Options: DENY`
(`X_FRAME_OPTIONS = "SAMEORIGIN"` to allow same-origin framing). Existing
headers are never overwritten.

## CSRF protection

`CsrfMiddleware` guards every unsafe method (`POST`, `PUT`, `PATCH`,
`DELETE`):

1. A per-session secret token is created lazily and stored in
   `session["_csrf_token"]`.
2. Requests must present it either as the `csrfmiddlewaretoken` **form
   field** or the `X-CSRFToken` **header** — the header being the natural
   fit for HTMX calls.
3. Over HTTPS the `Origin` (or `Referer`) must match the host or be listed
   in `CSRF_TRUSTED_ORIGINS`.

Include the token in every form you write:

```python
from ronnie.middleware.csrf import CsrfToken

@rt
def new(req):
    return Form(CsrfToken(req), Input(name="title"),
                action=save, method="post")
```

For header-based flows (e.g. `hx-post` from buttons rather than forms),
expose it once and read it client-side:

```python
from ronnie.middleware.csrf import csrf_token, hx_csrf_headers

Div(id="csrf", hx_headers=hx_csrf_headers(csrf_token(req)), style="display:none")
```

Failures get a 403 page explaining the reason.

### Exempting a handler

Some endpoints (webhooks from third parties) legitimately cannot send
tokens. Mark them:

```python
from ronnie.middleware.csrf import csrf_exempt

@rt
@csrf_exempt
def stripe_webhook(req):
    ...   # verify the payload signature yourself instead!
```

The exemption is collected when routes are mounted and matches that exact
route (path parameters included), so `@csrf_exempt` on
`/hooks/{token}` exempts `/hooks/anything` but nothing else. As a fallback
for non-routed paths, `CSRF_EXEMPT_PATHS` accepts regexes.

### Settings

| Setting | Default |
|---|---|
| `CSRF_TRUSTED_ORIGINS` | `[]` — e.g. `["https://app.example.com"]` |
| `CSRF_EXEMPT_PATHS` | `[]` (regex strings) |

## HTML output

FastHTML escapes text content by construction, so the classic
template-injection footguns are structurally absent. The remaining rule:
never build FT components by concatenating untrusted strings — pass
untrusted data as component children or attribute values, where it is
escaped.
