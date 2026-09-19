# Admin

The admin app generates a management interface for your tables: lists with
search, filters, sorting and pagination; create/edit forms; delete
actions — all staff-only and CSRF-protected.

## Getting started

```python
INSTALLED_APPS = [
    "ronnie.contrib.sessions",
    "ronnie.contrib.auth",       # login required
    "ronnie.contrib.messages",   # feedback after every action
    "ronnie.contrib.admin",
    "apps.blog",
]
```

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver       # admin at /admin/
```

## Registering tables

```python
# apps/blog/admin.py  (auto-discovered when the admin app is installed)
from ronnie.contrib.admin import ModelAdmin, register

from .models import Post

@register(Post)
class PostAdmin(ModelAdmin):
    list_display = ("title", "author", "published_at", "is_public")
    list_filter = ("is_public",)
    search_fields = ("title", "summary")
    ordering = ("-published_at",)
    list_per_page = 25
```

Equivalently, without a class:

```python
from ronnie.contrib.admin import site
site.register(Post, search_fields=("title",))
```

## ModelAdmin options

| Option | Effect |
|---|---|
| `list_display` | Columns of the changelist (default: first five fields) |
| `list_filter` | Fields rendered as a filter sidebar |
| `search_fields` | Case-insensitive substring search across these fields |
| `ordering` | Default sort; prefix `-` for descending |
| `list_per_page` | Page size (default 100) |
| `fields` | Ordered subset of editable fields |
| `exclude` | Fields hidden from the form |
| `readonly_fields` | Displayed but not editable |
| `empty_value_display` | Cell text for `None`/empty (default `—`) |
| `actions` | Bulk actions offered by the selector (default: `delete_selected`) |

## Hooks

```python
class PostAdmin(ModelAdmin):
    def get_queryset(self, request):
        rows = super().get_queryset(request)
        return [r for r in rows if r.tenant_id == request.scope["user"].id]

    def save_model(self, request, obj, change):
        if not change:
            obj.author = request.scope["user"].username
        return super().save_model(request, obj, change)

    def message_user(self, request, message, level="success"):
        ...  # defaults to the messages framework
```

| Hook | Called when |
|---|---|
| `get_queryset(request)` | Building the changelist |
| `save_model(request, obj, change)` | Insert (`change=False`) or update (`True`) |
| `delete_model(request, obj)` | Row deletion |
| `has_permission(request, action)` | Any admin view (default: `is_staff`) |

## The generated interface

| URL | Page |
|---|---|
| `/admin/` | Index of registered tables by app |
| `/admin/{app}/{model}/` | Changelist (`?q=`, `?f=&v=` filter, `?o=` sort, `?page=`) |
| `/admin/{app}/{model}/add` | Create form |
| `/admin/{app}/{model}/{pk}/change` | Edit form |
| `/admin/{app}/{model}/{pk}/delete` | Delete (redirects back) |
| `/admin/{app}/{model}/action` | Bulk action POST (`delete_selected`) |

Forms are introspected from the row dataclass annotations — numbers,
booleans, dates and strings map to the right inputs, the primary key is
managed for you. The UI is Pico CSS plus HTMX: header clicks sort, the
search box debounces, no bespoke JavaScript.

## Registering other apps' tables

Tables from framework apps register themselves when both apps are
installed — for example `ronnie.contrib.redirects` exposes its redirect
table for direct editing. To register a table that lives in an app you
don't control, do it from one of *your* apps' `admin.py` modules.

## Access rules

Every admin page requires a **staff** user; others are redirected to the
login page with a `next` parameter. The admin posts through the standard
[CSRF](security.md#csrf-protection) machinery — its forms already include
the token.
