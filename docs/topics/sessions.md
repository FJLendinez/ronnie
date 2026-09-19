# Sessions

Sessions give requests memory: a logged-in user, a shopping cart, a wizard's
step counter. Ronnie's session middleware loads a plain dict into the
request scope and persists it after the response — handlers just use the
`sess` parameter.

## Using sessions

```python
@rt
def counter(sess):
    sess["visits"] = sess.get("visits", 0) + 1
    return P(f"visits: {sess['visits']}")
```

- `sess` is a dict; assign to it and it persists.
- Sessions persist only when **modified** — mutating a nested structure in
  place doesn't count; assign the whole value.
- Keys starting with `_` are reserved for the framework (`_csrf_token`,
  `_auth_user_id`, …).

## Engines

`SESSION_ENGINE` picks where data lives:

| Engine | Storage | Best for |
|---|---|---|
| `"cookie"` *(default)* | Signed cookie on the client | Zero setup, small payloads |
| `"db"` | `ronnie_session` table | Server-side data, revocable sessions |
| `"cache"` | A cache alias | Fast, ephemeral (data dies with the cache) |
| dotted path | Your own engine | Anything else |

A custom engine implements `load(key)`, `save(key, data, max_age)`,
`delete(key)`, `new_key()` and `clear_expired()`:

```python
class VaultSessionEngine:
    def new_key(self) -> str: ...
    def load(self, session_key: str) -> dict | None: ...
    def save(self, session_key: str, data: dict, max_age: int) -> None: ...
    def delete(self, session_key: str) -> None: ...
    def clear_expired(self) -> int: ...

SESSION_ENGINE = "myproject.engines.VaultSessionEngine"
```

### The db engine

```python
INSTALLED_APPS = [..., "ronnie.contrib.sessions"]
SESSION_ENGINE = "db"
```

Run `python manage.py migrate` to create the table. Expired rows are never
read, but nothing deletes them by itself — schedule the command:

```bash
# cron: hourly
python manage.py clearsessions
```

### The cache engine

```python
CACHES = {"default": {"BACKEND": "ronnie.cache.backends.redis.RedisCache",
                      "LOCATION": "redis://…"}}
SESSION_ENGINE = "cache"
SESSION_CACHE_ALIAS = "default"      # which CACHES entry to use
```

Expiry rides on the cache TTL, so `clearsessions` is a no-op here. Beware:
flushing the cache logs everyone out.

## Cookie settings

| Setting | Default |
|---|---|
| `SESSION_COOKIE_NAME` | `"ronnie_session"` |
| `SESSION_COOKIE_AGE` | `1209600` (two weeks, seconds) |
| `SESSION_COOKIE_DOMAIN` | `None` — beware: setting it shares sessions across subdomains |
| `SESSION_COOKIE_SECURE` | `False` → set `True` under HTTPS |
| `SESSION_COOKIE_SAMESITE` | `"lax"` |

Cookies are always `HttpOnly` and set only when the session is created or
modified.

## Helpers

```python
from ronnie.contrib.sessions import flush, cycle_key
```

- **`flush(request)`** — destroy the session completely (data + cookie).
  Call it on logout.
- **`cycle_key(request)`** — issue a fresh key keeping the data. The
  authentication system calls it automatically on login, which is what
  makes session-fixation attacks ineffective with the db engine. With the
  cookie engine the payload is client-side, so there is no key to cycle.

## Choosing an engine

- Default to `"cookie"`: no infrastructure, works on every deployment.
- Move to `"db"` when you must revoke sessions server-side (banning a user
  mid-session) or store more than a few kilobytes.
- `"cache"` fits read-heavy, short-lived sessions behind a shared Redis.

Whatever the engine, session identifiers travel **only** in cookies —
never in URLs, where they leak through referrers and logs.
