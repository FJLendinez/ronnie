# Routing

Every installed app exposes handlers through a `Router` in its `routes.py`
(or `views.py`). Ronnie mounts them automatically when the application is
built — there is no central URL table to maintain.

## The import surface

Ronnie mirrors the underlying FT package module by module, so imports keep
the shape you already know — under Ronnie's own namespace:

| Mirror | Contents |
|---|---|
| `ronnie.common` | The curated everyday surface: components (`P`, `Titled`, `Form`, …), app factories (`fast_app`, `serve`), responses (`Redirect`), request helpers, plus Ronnie's `Router`, `CsrfToken`, `csrf_exempt`, `Alerts`, `HumanTime` |
| `ronnie.core` | The engine: `FastHTML`, `APIRouter`, `to_xml`, response internals — merged with Ronnie's own core (`management`, `routing`, `checks`, `signing`, `passwords`, `asgi`, `signals`) |
| `ronnie.components` | Every HTML component |
| `ronnie.svg` | The full SVG component set (`Svg`, `Circle`, `Rect`, `Animate`, …) |
| `ronnie.pico` | Pico components (`Card`, `Grid`, `Group`, `DialogX`, …) |
| `ronnie.xtend` | Sitemap builders (`Urlset`, `Url`) and `use_kwargs` |
| `ronnie.oauth` | OAuth clients (`GitHubAppClient`, `GoogleAppClient`, `consent_url`, …) |
| `ronnie.jupyter`, `ronnie.live_reload`, `ronnie.toaster`, `ronnie.js`, `ronnie.ft`, `ronnie.cli`, `ronnie.basics`, `ronnie.authmw`, `ronnie.fastapp`, `ronnie.starlette` | Their exact counterparts |
| `ronnie.stripe_otp` | Mirror of the optional module — derives nothing until `stripe` is installed |

```python
from ronnie.common import P, Redirect, Router, Titled, serve
from ronnie.pico import Card, Grid
from ronnie.svg import Circle, Svg
```

`ronnie.common` stays deliberately **curated** (module-specific vocabularies
live in their mirrors), and every mirror derives every public attribute of
its counterpart — including names resolved lazily. Application code never
imports the underlying package directly.

## Declaring routes

```python
# apps/blog/routes.py
from ronnie.common import P, Titled

from ronnie.core.routing import Router

rt = Router("blog")   # prefix: every path below becomes /blog/…


@rt
def index():
    return Titled("Blog", P("posts live here"))


@rt
def archive(year: int):
    return P(f"archive for {year}")
```

`Router("blog")` normalizes the prefix, so `index` answers `/blog/` and
`archive` answers `/blog/archive?year=2026`. Handlers are ordinary FastHTML
functions: annotate the parameters you expect to be bound (path, query,
form, cookies, headers) and return FT components.

### Verb-specific handlers

When one path needs separate read/write handlers, name them `get` and
`post` — FastHTML maps those names to their HTTP verbs automatically:

```python
@rt("/comment")
def get():
    return comment_form()

@rt("/comment")
def post(req, comment: CommentForm):
    save(comment)
    return Redirect("/blog")
```

Any other handler name registers for **both** GET and POST.

### Referencing routes

The object returned by `@rt` is a route function: use it directly in
`href`/`action`/`hx_get`, and `.to(...)` when you need query parameters:

```python
@rt
def show(req, id: int):
    ...

Button("Open", hx_get=show.to(id=3))
A("Post 3", href=show.to(id=3))
```

Prefer these references over hard-coded URL strings; renaming a handler then
renames the URL everywhere.

## Mounting and conflict detection

When `get_asgi_application()` builds the ASGI app it walks
`INSTALLED_APPS` in order, imports each `<app>.routes` (falling back to
`<app>.views`) and mounts every `Router` found in the module namespace.

Two handlers claiming the same path **and** verb raise
`ImproperlyConfigured` at startup — you get a clear error naming both apps
instead of a silently shadowed route. A `get`/`post` pair on one path is fine
because their verbs don't overlap.

## Static files

Set `STATIC_URL` and `STATIC_ROOT` and Ronnie mounts a static file handler
when the directory exists:

```python
STATIC_URL = "/static"
STATIC_ROOT = BASE_DIR / "static"
```

During development `python manage.py runserver` serves these directly; in
production put a real web server or CDN in front (the mount remains as a
fallback).

## The ASGI entry point

`config/asgi.py` is the bridge between your project and any ASGI server:

```python
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ.setdefault("RONNIE_SETTINGS_MODULE", "myproject.config.settings")

from ronnie.core.asgi import get_asgi_application

application = get_asgi_application()
```

`get_asgi_application()` boots settings and the app registry, resolves the
[MIDDLEWARE](middleware.md) stack, mounts app routers and static files, and
installs friendly 404/500 pages. Run it with any ASGI server:

```bash
uvicorn myproject.config.asgi:application --factory false
```
