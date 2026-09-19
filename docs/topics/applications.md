# Applications

An **application** is a Python package that bundles one slice of your
project: routes, tables, templates-as-components, tests and commands. Ronnie
projects are a list of such packages — small, focused and independently
testable.

## Project layout

`ronnie startproject mysite` creates:

```
mysite/
├── manage.py                 # CLI shim → ronnie.core.management
├── config/
│   ├── settings.py
│   └── asgi.py               # application = get_asgi_application()
└── apps/
    └── blog/                 # ronnie startapp blog
        ├── __init__.py
        ├── apps.py           # BlogConfig(AppConfig)
        ├── routes.py         # handlers (auto-discovered)
        ├── models.py         # row dataclasses + TABLES
        ├── tests/
        └── management/commands/
```

Create a new app from the project root:

```bash
python manage.py startapp blog      # lands in apps/, import path apps.blog
```

Then add `"apps.blog"` to `INSTALLED_APPS` and `ronnie migrate` creates its
tables.

## INSTALLED_APPS

```python
INSTALLED_APPS = [
    "ronnie.contrib.sessions",
    "ronnie.contrib.auth",
    "ronnie.contrib.messages",
    "ronnie.contrib.admin",
    "apps.blog",
    "apps.billing",
]
```

Each entry is either a package path or an explicit config class path
(`"apps.blog.apps.BlogConfig"`). Order matters: routes are mounted in list
order, later apps may not re-declare a route an earlier app already claimed,
and management commands from earlier apps override later ones.

## AppConfig

Per-app metadata and lifecycle live in `apps.py`:

```python
from ronnie.apps import AppConfig

class BlogConfig(AppConfig):
    name = "apps.blog"       # full import path (required when declared)
    label = "blog"           # default: last component of name; must be unique
    verbose_name = "Blog"    # default: label.title()

    def ready(self):
        # Runs once, after every app's models and tasks modules are imported.
        # Connect signals, register extra admin models, warm caches…
        from . import signals  # noqa: F401
```

| Attribute | Default | Purpose |
|---|---|---|
| `name` | — | Full dotted path of the package |
| `label` | last component of `name` | Short unique identifier (used in admin URLs, permissions) |
| `verbose_name` | `label.title()` | Human-readable name |
| `path` | auto-detected | Filesystem location of the package |
| `models_module` | auto | The app's `models` module, if any |

If `apps.py` contains exactly one `AppConfig` subclass it is used
automatically; with several, exactly one must set `default = True`.

### The `ready()` hook

`ready()` is the place for import-time side effects that must happen **after**
the registry is complete:

```python
def ready(self):
    from ronnie.core.signals import request_finished
    request_finished.connect(close_pool, dispatch_uid="blog-close")
```

Keep it idempotent, don't touch the database in it, and import app modules
lazily (inside the method) rather than at `apps.py` module level.

## The app registry

Loading happens in three phases, in `INSTALLED_APPS` order:

1. Import each entry and instantiate its `AppConfig`.
2. Import every app's `models` **and** `tasks` submodules (this registers
   tables and `@task` functions).
3. Call every `ready()` hook.

The registry is available everywhere:

```python
from ronnie.apps import apps

apps.ready                      # True once populate finished
apps.get_app_config("blog")     # → BlogConfig (LookupError if unknown)
apps.get_app_configs()          # iterator in INSTALLED_APPS order
apps.is_installed("apps.blog")  # True/False
```

## Conventions inside an app

| File | Auto-discovered? | Contents |
|---|---|---|
| `routes.py` (or `views.py`) | yes | Handlers mounted under the app's prefix |
| `models.py` | yes | Row dataclasses + `TABLES: list[type]` |
| `tasks.py` | yes | `@task` functions |
| `admin.py` | yes (when the admin app is installed) | `@register(...)` classes |
| `management/commands/*.py` | yes | One `Command` class per file |
| `tests/` | collected by `ronnie test` | Your test suite |

None of these are magic: they are ordinary modules Ronnie imports at
well-defined moments so your app only needs to exist to be wired in.
