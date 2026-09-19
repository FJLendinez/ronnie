# Settings reference

Every setting Ronnie understands, with its default. Your project's
`config/settings.py` overrides any of them; anything else you define is
yours (prefix it to avoid future collisions).

## Core

| Setting | Default | Meaning |
|---|---|---|
| `DEBUG` | `False` | Development mode: verbose errors, localhost hosts allowed |
| `SECRET_KEY` | `""` | Signs sessions, tokens, cookies — required in production |
| `SECRET_KEY_FALLBACKS` | `[]` | Verify-only keys during rotation |
| `ALLOWED_HOSTS` | `[]` | Permitted `Host` values; `".dom.com"` covers subdomains |
| `INSTALLED_APPS` | `[]` | Apps to load (order matters) |
| `MIDDLEWARE` | `[]` | Request pipeline (dotted paths, outermost first) |
| `TIME_ZONE` | `"UTC"` | Reference timezone for your code |
| `USE_TZ` | `True` | Prefer timezone-aware datetimes |
| `LANGUAGE_CODE` | `"en"` | Default language tag |
| `STATIC_URL` | `"/static"` | URL prefix for static files |
| `STATIC_ROOT` | `None` | Directory mounted at `STATIC_URL` when it exists |
| `LOGGING` | `None` | dict-config passed to `logging.config.dictConfig` |

## Security

| Setting | Default | Meaning |
|---|---|---|
| `SECURE_HSTS_SECONDS` | `0` | HSTS max-age (0 disables the header) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | Append `includeSubDomains` |
| `SECURE_HSTS_PRELOAD` | `False` | Append `preload` |
| `SECURE_SSL_REDIRECT` | `False` | 301 http→https |
| `SECURE_SSL_HOST` | `None` | Redirect target host |
| `SECURE_REDIRECT_EXEMPT` | `[]` | Regexes exempt from the redirect |
| `SECURE_PROXY_SSL_HEADER` | `None` | `("X-Forwarded-Proto", "https")` behind a proxy |
| `SECURE_REFERRER_POLICY` | `"same-origin"` | `Referrer-Policy` header |
| `SECURE_CROSS_ORIGIN_OPENER_POLICY` | `"same-origin"` | COOP header |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | `X-Content-Type-Options: nosniff` |
| `USE_X_FORWARDED_HOST` | `False` | Validate `X-Forwarded-Host` instead of `Host` |
| `X_FRAME_OPTIONS` | `"DENY"` | Clickjacking header value |
| `CSRF_TRUSTED_ORIGINS` | `[]` | Extra origins accepted on HTTPS checks |
| `CSRF_EXEMPT_PATHS` | `[]` | Regexes of paths exempt from CSRF |
| `CSRF_COOKIE_NAME` | `"csrftoken"` | Reserved for cookie-based token flows |
| `CSRF_COOKIE_SECURE` / `...SAMESITE` / `...HTTPONLY` | `False` / `"Lax"` / `False` | Cookie flags |

## Passwords

| Setting | Default | Meaning |
|---|---|---|
| `PASSWORD_HASHERS` | `[PBKDF2, Scrypt]` | First encodes; all verify |
| `AUTH_PASSWORD_VALIDATORS` | `None` | `NAME`/`OPTIONS` dicts; `None` = the four defaults |

## Sessions

| Setting | Default | Meaning |
|---|---|---|
| `SESSION_ENGINE` | `"cookie"` | `"cookie"`, `"db"`, `"cache"` or a dotted engine path |
| `SESSION_CACHE_ALIAS` | `"default"` | Cache alias for the cache engine |
| `SESSION_COOKIE_NAME` | `"ronnie_session"` | Cookie name |
| `SESSION_COOKIE_AGE` | `1209600` | Lifetime in seconds (two weeks) |
| `SESSION_COOKIE_DOMAIN` | `None` | Shared-subdomain cookies (use with care) |
| `SESSION_COOKIE_SECURE` | `False` | `Secure` flag (set `True` under HTTPS) |
| `SESSION_COOKIE_SAMESITE` | `"lax"` | SameSite attribute |

## Authentication

| Setting | Default | Meaning |
|---|---|---|
| `AUTH_USER_MODEL` | `"ronnie.contrib.auth.User"` | Dotted path to your user dataclass |
| `AUTHENTICATION_BACKENDS` | `[ModelBackend]` | Tried in order |
| `LOGIN_URL` | `"/accounts/login"` | Where `@login_required` sends visitors |
| `LOGIN_REDIRECT_URL` | `"/"` | After sign-in (unless `?next=`) |
| `LOGOUT_REDIRECT_URL` | `"/"` | After sign-out |

## Messages

| Setting | Default | Meaning |
|---|---|---|
| `MESSAGE_STORAGE` | `FallbackStorage` | `session`, `cookie` or fallback class path |
| `MESSAGE_LEVEL` | `20` | Minimum level kept (30 keeps warning+) |
| `MESSAGE_TAGS` | `{}` | Level→tag overrides, e.g. `{25: "win"}` |

## Cache

| Setting | Default | Meaning |
|---|---|---|
| `CACHES` | `{"default": locmem}` | Aliases → backend configuration |
| `CACHE_MIDDLEWARE_ALIAS` | `"default"` | Alias used by the per-site middleware |
| `CACHE_MIDDLEWARE_SECONDS` | `600` | Per-site TTL |
| `CACHE_MIDDLEWARE_KEY_PREFIX` | `""` | Prefix for per-site keys |

`CACHES` entries accept `BACKEND`, `LOCATION`, `TIMEOUT`, `KEY_PREFIX`,
`VERSION`, `KEY_FUNCTION` and `OPTIONS` (`MAX_ENTRIES`,
`CULL_FREQUENCY`) — see [the cache topic](../topics/cache.md).

## Tasks

| Setting | Default | Meaning |
|---|---|---|
| `TASKS_BROKER` | `InlineBroker` | `inline`, `thread`, `redis` classes |
| `TASKS_BROKER_URL` | `None` | Redis URL for the redis broker |
| `TASKS_RESULT_BACKEND` | `"cache:default"` | Where `AsyncResult` reads/writes |
| `TASKS_DEFAULT_QUEUE` | `"default"` | Queue used by `.delay()` |
| `TASKS_MAX_RETRIES` | `0` | Default retry budget per task |
| `TASKS_RETRY_BACKOFF` | `True` | Exponential backoff between attempts |
| `TASKS_SCHEDULE` | `{}` | Beat entries: `{"task": …, "every": seconds}` |

## Admin & humanize

| Setting | Default | Meaning |
|---|---|---|
| `ADMIN_URL` | `"/admin"` | Reserved: URL prefix of the admin |
| `ADMIN_SITE_HEADER` | `"Ronnie Administration"` | Header text |
| `HUMANIZE_LANGUAGE` | `"es"` | `"es"` or `"en"` |
