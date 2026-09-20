# Ronnie

**All the batteries of a full-stack framework on top of [FastHTML](https://fastht.ml).**

Ronnie keeps everything that makes FastHTML a joy — first-class Python HTML
components, HTMX-first interactivity, signature-driven handlers, the
MiniDataAPI — and adds the structure that large, long-lived applications need:

- **Settings & applications** — a lazy settings object, a per-app registry
  with lifecycle hooks, and file conventions that scale with your team.
- **Management commands** — a `manage.py` CLI with per-app command
  autodiscovery and a system-checks framework.
- **Security built in** — security headers, host validation, CSRF, request
  signing, password hashing and validation, on by default.
- **Batteries** — authentication, sessions, flash messages, an
  auto-generated admin, humanization helpers and DB-backed redirects.
- **Cache framework** — one API over local memory, files or Redis.
- **Test framework** — an ergonomic test client, settings overrides and
  per-test throwaway databases.
- **Background tasks** — `@task` decorators, pluggable brokers, retries with
  backoff, workers and a periodic scheduler.

## Installation

```bash
pip install python-ronnie            # the import name is `ronnie`
```

Optional extras:

```bash
pip install 'python-ronnie[redis]'    # Redis cache + task broker
pip install 'python-ronnie[argon2]'   # Argon2 password hashing
pip install 'python-ronnie[postgres]' # PostgreSQL via the MiniDataAPI
```

## Your first project

```bash
ronnie startproject mysite
cd mysite
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

That gives you signed-cookie sessions, a login system, CSRF protection,
security headers and a working admin at `/admin/` — before you write a single
line.

## A ten-second tour

Handlers are plain typed functions; every import comes from Ronnie's own
`ronnie.common` surface (a direct derivation of the FT stack, extended with
Ronnie's components):

```python
# apps/blog/routes.py
from ronnie.common import P, Titled
from ronnie.core.routing import Router

rt = Router("blog")

@rt
def index():
    return Titled("Blog", P("hello from ronnie"))
```

```python
# apps/blog/admin.py — instant CRUD for the table above
from ronnie.contrib.admin import ModelAdmin, register
from .models import Post

@register(Post)
class PostAdmin(ModelAdmin):
    list_display = ("title", "published_at")
    search_fields = ("title",)
```

```python
# anywhere: settings, cache and tasks
from ronnie.conf import settings
from ronnie.cache import cache
from ronnie.tasks import task

@task(max_retries=3)
def rebuild_index(post_id: int): ...

rebuild_index.delay(post_id=42)
cache.get_or_set("warm", True, timeout=60)
```

## Where to go next

Start with [Settings](topics/settings.md) and
[Applications](topics/applications.md) to understand the project layout, then
[Routing](topics/routing.md) to write your first handlers. The
[Settings reference](reference/settings.md) lists every knob in one place.

## Design principles

1. **Composition, not replacement.** Ronnie configures FastHTML; it never
   patches it. Your handlers stay ordinary, typed functions.
2. **The signature is the contract.** Nothing in Ronnie hides a handler's
   parameters; middleware communicates through the request scope.
3. **Batteries are optional.** Every contrib package is an app you list in
   `INSTALLED_APPS` — remove it and the rest keeps working.
4. **Secure by default, explicit in production.** Development works with zero
   configuration; `ronnie check --deploy` tells you exactly what to harden.
