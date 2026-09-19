# Ronnie

**All the batteries of Django on top of FastHTML.**

Ronnie layers Django's battle-tested patterns onto FastHTML — everything you
love about FastHTML (FT components, HTMX, signature-driven handlers, the
MiniDataAPI) plus everything you need at scale:

| Django brings | Ronnie |
|---|---|
| `DJANGO_SETTINGS_MODULE` / `django.conf.settings` | `RONNIE_SETTINGS_MODULE` / `ronnie.conf.settings` (lazy, callables, `override_settings`) |
| Apps & `AppConfig.ready()` | same, with 3-phase populate and per-app `routes.py` autodiscovery |
| `manage.py` commands | `manage.py` / `ronnie` CLI: `startproject`, `startapp`, `migrate`, `check [--deploy]`, `runserver`, `shell`, `test`, `createsuperuser`, `changepassword`, `clearsessions`, `worker`, `beat`, `diffsettings`, `version` |
| Security middleware stack | security headers, host validation, CSRF, clickjacking, signing (`Signer`/`TimestampSigner`), PBKDF2/scrypt/argon2 hashers, the 4 password validators |
| `django.contrib.auth` | users + backends + `login()/logout()`, `/accounts/*` views, `@login_required`, session-hash invalidation |
| `django.contrib.sessions` | pluggable engines: signed cookie (default), db, cache |
| `django.contrib.messages` | levels/tags, session/cookie/fallback storages, `Alerts()` component |
| `django.contrib.admin` | `ModelAdmin` + `site.register`, CRUD with search/filter/sort/pagination/actions, HTMX + Pico |
| `django.contrib.humanize` | 6 helpers with **es/en** locales + `HumanTime()` |
| `django.contrib.redirects` | db-backed 404 fallback (301/302/410), managed from the admin |
| `django.core.cache` | `CACHES` / `caches["alias"]`, locmem/file-based/redis/dummy, `cache_page`, per-site middleware, fragment caching |
| `django.test` | `RonnieTestClient`, `RonnieTestCase`, `override_settings`, `assertRedirects/assertContains`, pytest fixtures (`client`, `db`) |
| Celery-ish tasks | `@task` + `.delay()`, brokers inline/thread/redis, `AsyncResult`, retries with backoff, `ronnie worker`/`ronnie beat` |

## Quickstart

```bash
pip install python-ronnie          # import name: ronnie
ronnie startproject mysite         # full stack: sessions, auth, messages, admin, redirects
cd mysite
python manage.py migrate
python manage.py createsuperuser --noinput   # or interactive
python manage.py runserver
```

## A taste

```python
# apps/blog/routes.py — plain FastHTML handlers, zero framework ceremony
from fasthtml.common import P, Titled
from ronnie.core.routing import Router

rt = Router("blog")

@rt
def index():
    return Titled("Blog", P("hello from ronnie"))
```

```python
# apps/blog/admin.py — instant CRUD
from ronnie.contrib.admin import ModelAdmin, register
from .models import Post

@register(Post)
class PostAdmin(ModelAdmin):
    list_display = ("title", "published_at")
    search_fields = ("title",)
```

```python
# anywhere: settings, cache, tasks
from ronnie.conf import settings
from ronnie.cache import cache
from ronnie.tasks import task

@task(max_retries=3)
def rebuild_index(post_id: int): ...

rebuild_index.delay(post_id=42)
cache.get_or_set("warm", True, timeout=60)
```

```python
# tests
from ronnie.testing import RonnieTestCase, override_settings

class PostTests(RonnieTestCase):     # throwaway sqlite DB per test
    def test_index(self):
        r = self.client.get("/blog/")
        self.assertContains(r, "hello from ronnie")
```

## Design notes

- **Composition over fork**: Ronnie configures FastHTML, never patches it
  (see `engineering/fasthtml-0.14-spike.md` for the integration contract).
- **No ORM**: tables are dataclasses over the MiniDataAPI (`TABLES` in each
  app's `models.py`; `ronnie migrate` creates/updates them).
- **Django-format compatible** password hashes and signatures.
- Extras: `ronnie[redis]`, `ronnie[argon2]`, `ronnie[postgres]`.

## Status

Alpha (see [PLAN.md](PLAN.md) for the roadmap and per-phase decisions).
Tested with 265+ tests, `mypy --strict` clean, ruff clean.

## License

MIT
