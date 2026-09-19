# Ronnie

**All the batteries of Django on top of FastHTML.**

Ronnie is a framework layer that brings Django's battle-tested patterns to
FastHTML applications at scale, without giving up anything that makes
FastHTML great (FT components, HTMX, signature-driven handlers, MiniDataAPI):

- **Settings & apps** — `RONNIE_SETTINGS_MODULE`, lazy settings, app registry
  with `AppConfig.ready()`, exactly like Django.
- **Management commands** — `python manage.py <command>` with per-app
  autodiscovery (`<app>/management/commands/`), `call_command`, `ronnie check`.
- **Built-in security** — security headers, host validation, CSRF,
  password hashing/validation, signing.
- **contrib packages** — `admin`, `auth`, `humanize`, `messages`,
  `redirects`, `sessions`.
- **Cache framework** — pluggable backends (locmem, file-based, Redis, dummy).
- **Test framework** — test client, `override_settings`, assertions, pytest plugin.
- **Tasks framework** — `@task` decorator, pluggable brokers, `ronnie worker`
  and `ronnie beat`.

## Status

Work in progress — see [PLAN.md](PLAN.md) for the full build plan.

## Quick peek

```python
# apps/blog/routes.py
from ronnie.core.routing import Router

rt = Router("blog")

@rt
def index():
    return Ul(Li(p.title) for p in published_posts())
```

```python
# anywhere
from ronnie.conf import settings

if settings.DEBUG:
    ...
```

## License

MIT
