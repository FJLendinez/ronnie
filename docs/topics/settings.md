# Settings

Ronnie settings are plain Python modules with UPPERCASE variables. A lazy
settings object gives every part of your code the same view of them, and a
defaults module means you only configure what you want to change.

## The settings module

A project created with `ronnie startproject` ships `config/settings.py`:

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "…"
DEBUG = True
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS: list[str] = [
    "ronnie.contrib.sessions",
    "ronnie.contrib.auth",
    # "apps.blog",
]

DATABASES = {
    "default": {"ENGINE": "sqlite", "NAME": BASE_DIR / "db.sqlite3"},
}
```

Anything Python can express works here: loops, imports, `os.environ`
lookups. Only UPPERCASE attributes are considered settings.

### Selecting the module

Resolution order:

1. `ronnie.setup("myproject.config.settings")` — explicit.
2. The `RONNIE_SETTINGS_MODULE` environment variable (this is what
   `manage.py` sets with `os.environ.setdefault`).

```bash
RONNIE_SETTINGS_MODULE=myproject.config.settings ronnie check
ronnie check --settings=myproject.config.settings   # equivalent, per-command
```

## Reading settings

```python
from ronnie.conf import settings

if settings.DEBUG:
    ...
```

Rules of the road:

- Access is **lazy**: nothing is imported until the first attribute read.
- Values are read from your module first; anything missing falls back to the
  framework defaults (`ronnie/global_settings.py`).
- **Callable settings are evaluated on first access** and the result is
  cached — a setting may be a factory function:

  ```python
  def CACHES():
      return {"default": {"BACKEND": "..."}}
  ```

- Don't mutate settings at runtime. Tests swap them with
  [`override_settings`](testing.md#overriding-settings), which is the
  supported mechanism.
- `from ronnie.conf.settings import DEBUG` does **not** work — `settings`
  is an object, not a module. Always attribute-access it.

Useful introspection helpers:

| Attribute / command | Meaning |
|---|---|
| `settings.SETTINGS_MODULE` | dotted path of the active module |
| `settings.configured` | `True` once settings are loaded |
| `ronnie diffsettings` | prints every value that differs from the defaults |

## Programmatic configuration

For scripts and one-off tooling you can skip the module entirely:

```python
import ronnie

ronnie.setup()                       # uses RONNIE_SETTINGS_MODULE
# …or without any module:
from ronnie.conf import settings
settings.configure(DEBUG=True, SECRET_KEY="dev-only")
ronnie.setup()
```

`configure()` may be called exactly once and before anything reads settings;
afterwards the object is immutable-by-convention.

## Split settings

Because settings are modules, splitting by environment is just imports:

```
config/
├── settings.py        # imports from base.py, overrides for local dev
├── base.py            # shared configuration
└── production.py      # DEBUG=False, real hosts, keys from the environment
```

```python
# config/production.py
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["example.com"]
SECRET_KEY = __import__("os").environ["SECRET_KEY"]
```

Select it with `RONNIE_SETTINGS_MODULE=config.production`.

## Namespacing your own settings

Settings written by reusable apps should be prefixed to avoid collisions —
pick a prefix and document it:

```python
# Your app reads one prefixed setting
BLOG_POSTS_PER_PAGE = 20
```

Everything Ronnie itself defines is documented in the
[settings reference](../reference/settings.md); anything not listed there is
fair game for your prefix.
