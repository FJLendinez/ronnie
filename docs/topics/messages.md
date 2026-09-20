# Messages

Flash messages are one-shot notifications that survive a redirect: "Post
saved", "Checkout failed", "Welcome back". The messages app stores them
during one request and renders (and clears) them in the next.

## Usage

```python
from ronnie.contrib.messages import messages
from ronnie.common import Redirect

@rt
def save(req):
    posts.insert(...)
    messages.success(req, "Post saved.")
    messages.warning(req, "It will be public immediately.", extra_tags="banner")
    return Redirect(index)
```

Levels mirror the classic five-step scale:

| Function | Level | Default tag |
|---|---|---|
| `messages.debug(req, ...)` | 10 | `debug` |
| `messages.info(req, ...)` | 20 | `info` |
| `messages.success(req, ...)` | 25 | `success` |
| `messages.warning(req, ...)` | 30 | `warning` |
| `messages.error(req, ...)` | 40 | `error` |

Messages below `MESSAGE_LEVEL` (default 20) are dropped — raise it to 30 in
production to silence info noise. `extra_tags` rides along into the
rendered class list.

## Rendering

```python
from ronnie.contrib.messages import Alerts   # also in ronnie.common

def page(req):
    return Titled("Blog", Alerts(req), Main(...))
```

`Alerts(req)` consumes pending messages and returns alert `<div>`s with
`role="alert"` and classes `alert <tags>`; with Pico's defaults that is
already readable, and `MESSAGE_TAGS` can rename any level's tag:

```python
MESSAGE_TAGS = {25: "win"}
```

Reading without rendering:

```python
from ronnie.contrib.messages import get_messages
for m in get_messages(request):      # consume=False to peek without clearing
    ...
```

## Storage

`MESSAGE_STORAGE` chooses where messages wait between requests:

| Storage | Where | Notes |
|---|---|---|
| `ronnie.contrib.messages.storage.FallbackStorage` *(default)* | Signed cookie, overflowing to the session | Fast when small, safe when big |
| `…storage.SessionStorage` | The session | Requires the session middleware |
| `…storage.CookieStorage` | Signed cookie only | Caps at ~2 KB per request |

A tampered or expired cookie is silently ignored, never an error.

### How the fallback works

Messages added during a request accumulate in the request scope; when the
response ships, the middleware writes them into the cookie — or, if the
signed payload would exceed 2048 bytes, into the session instead. Reading
consumes from both and clears them (expiring the cookie).

## Setup

```python
INSTALLED_APPS = [..., "ronnie.contrib.messages"]
MIDDLEWARE = [...,
    "ronnie.contrib.sessions.middleware.SessionMiddleware",   # before messages
    "ronnie.contrib.messages.middleware.MessagesMiddleware",
]
```

The middleware only needs to ship cookie headers — with pure session
storage it is effectively a no-op — but keep it in the list so storage can
be swapped without touching the stack.
