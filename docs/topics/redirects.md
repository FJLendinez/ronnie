# Redirects

URLs die and content moves. The redirects app stores old→new mappings in
the database and applies them automatically when a page would otherwise
404 — no code changes, no redeploy for each moved page.

## Setup

```python
INSTALLED_APPS = [..., "ronnie.contrib.redirects"]

MIDDLEWARE = [...,
    "ronnie.contrib.redirects.middleware.RedirectFallbackMiddleware",
]   # keep it LAST: it only ever intervenes on a 404
```

```bash
python manage.py migrate          # creates the redirect table
```

## How it works

When a response would be a 404, the middleware looks up the exact request
path:

| Row found | Response |
|---|---|
| `new_path` set, `response_code=301` | permanent redirect |
| `new_path` set, `response_code=302` *(default)* | temporary redirect |
| `new_path` empty | `410 Gone` — the page is gone on purpose |
| no row | the original 404 stands |

Query strings are **not** matched — lookups are by path only.

## Managing redirects

Install the [admin](admin.md) app and the redirect table appears there
automatically (`old_path`, `new_path`, `response_code`), ready for
copy-paste fixes by non-developers.

Programmatically it is an ordinary MiniDataAPI table:

```python
from ronnie.db import get_table
from ronnie.contrib.redirects import RonnieRedirect

get_table(RonnieRedirect, pk="old_path").insert(
    old_path="/ancient-url/",
    new_path="/posts/",
    response_code=301,
)
```

`old_path` is the primary key — one destination per source. Changing a
destination is an update, not a new row.

## Choosing codes

- **301** — permanent: search engines transfer ranking, browsers cache it
  aggressively. Use for settled moves.
- **302** — temporary: the old URL stays authoritative. Default for
  campaigns and experiments.
- **410** — deliberate deletion: tell crawlers to forget the URL instead
  of retrying forever.

## Notes

- The lookup costs one indexed query per 404 — effectively free on a
  healthy site, since 404s are the exception.
- Redirect chains (A→B→C) work but waste a round trip; collapse them when
  you notice them.
- For redirects you can express in code, prefer returning `Redirect(...)`
  from the handler — no database involved.
