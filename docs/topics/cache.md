# Cache framework

One API over several backends: memoize a function, cache a rendered page,
store a fragment every user shares. Configure with `CACHES`, access with
`caches`.

## Configuration

```python
CACHES = {
    "default": {
        "BACKEND": "ronnie.cache.backends.locmem.LocMemCache",
        "LOCATION": "www",                 # named pool (locmem) or directory/URL
        "TIMEOUT": 300,                    # default per-key expiry (seconds)
        "KEY_PREFIX": "www",
        "OPTIONS": {"MAX_ENTRIES": 300, "CULL_FREQUENCY": 3},
    },
    "redis": {
        "BACKEND": "ronnie.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    },
}
```

| Key | Meaning |
|---|---|
| `BACKEND` | Dotted path to the cache class |
| `LOCATION` | Backend-specific: pool name, directory or URL |
| `TIMEOUT` | Default expiry; `None` = never, per-key calls may override |
| `KEY_PREFIX` | Prepended to every key (multi-app isolation) |
| `VERSION` | Integer version baked into keys; bump to mass-invalidate |
| `KEY_FUNCTION` | Dotted path to a `(key, prefix, version) -> str` function |
| `OPTIONS` | Backend knobs: `MAX_ENTRIES`, `CULL_FREQUENCY` |

### Backends

| Backend | Storage | Use it for |
|---|---|---|
| `locmem.LocMemCache` *(default)* | Per-process dict | Development, single-process apps |
| `filebased.FileBasedCache` | Pickled files under `LOCATION` | Small deployments, no Redis |
| `redis.RedisCache` | Redis (`ronnie[redis]`) | Production, shared across processes |
| `dummy.DummyCache` | Nowhere | Disabling caching in tests |

Values must be picklable; keys are strings (longer than 250 characters or
containing spaces trigger warnings).

## Using a cache

```python
from ronnie.cache import cache, caches

cache.set("sidebar:top", html, timeout=600)   # default alias
cache.get("sidebar:top")                      # …or None
cache.get("key", "fallback")                  # default value
cache.add("lock:nightly", 1, timeout=3600)    # True only if it wasn't present
cache.get_or_set("stats", compute_stats, timeout=60)   # builder runs on miss
cache.touch("key", timeout=60)                # refresh TTL; False if absent
cache.delete("key")
cache.clear()                                 # whole cache (careful!)

cache.get_many(["a", "b"])                    # {"a": 1}
cache.set_many({"a": 1, "b": 2}, timeout=60)
cache.delete_many(["a", "b"])

cache.incr("hits")        # raises ValueError if missing
cache.decr("hits", 10)

shared = caches["redis"]  # another alias
```

## Caching responses

### Per-handler

```python
from ronnie.cache.http import cache_page

@rt
@cache_page(60)
def home():
    return expensive_homepage()     # rendered once per minute per URL
```

Only `GET` requests are cached; the key covers the path and query string.

### Per-site

Add the middleware to cache every `GET/HEAD 200` by URL:

```python
MIDDLEWARE = ["ronnie.cache.http.CacheMiddleware", ...]   # outermost
CACHE_MIDDLEWARE_ALIAS = "default"
CACHE_MIDDLEWARE_SECONDS = 600
CACHE_MIDDLEWARE_KEY_PREFIX = ""
```

### Cache-control headers

```python
from ronnie.cache.http import cache_control, no_cache

return no_cache(), Titled("Live scores", ...)                    # never cache
return cache_control(max_age=3600, private=True), page           # downstream hints
```

## Caching fragments

Cache the rendered XML of any FT fragment — ideal for sidebars and menus:

```python
from ronnie.cache.http import cache_fragment, make_fragment_key

def sidebar(user):
    key = make_fragment_key("sidebar", [str(user.id)])
    return Div(cache_fragment(key, 600, lambda: build_sidebar(user)))
```

Invalidate precisely by computing the same key and deleting it, or bump the
`VERSION` of the alias for a clean slate.

## Patterns worth copying

- **Read-through:** wrap expensive queries in `get_or_set` with a
  `timeout`, and delete the key whenever the underlying table changes
  (a signal receiver is a natural place).
- **Locks:** `add()` returns `True` for exactly one caller — a poor man's
  mutex for cron-ish jobs.
- **Counters:** `incr`/`decr` for rate-limit tallies; remember they raise
  on missing keys.
- **Don't cache authenticated pages per-user under a shared key.** Include
  the user (or role) in the key.
