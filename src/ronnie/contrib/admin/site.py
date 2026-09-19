"""AdminSite + ModelAdmin (a compact django.contrib.admin).

Register models from an app's ``admin.py``::

    from ronnie.contrib.admin import site, ModelAdmin, register
    from .models import Product

    @register(Product)
    class ProductAdmin(ModelAdmin):
        list_display = ("name", "price")
        search_fields = ("name",)
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ...db import get_table

__all__ = ["AdminSite", "ModelAdmin", "site"]


class ModelAdmin:
    """Options + hooks for one registered table."""

    list_display: tuple[str, ...] = ()
    list_display_links: tuple[str, ...] = ()
    list_filter: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()
    ordering: tuple[str, ...] = ()
    list_per_page: int = 100
    empty_value_display: str = "—"
    readonly_fields: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()  # subset of fields to show/edit; () = all
    exclude: tuple[str, ...] = ()
    actions: tuple[str, ...] = ("delete_selected",)

    def __init__(self, model: type, site: AdminSite) -> None:
        self.model = model
        self.site = site
        if not self.list_display:
            self.list_display = self._default_list_display()

    # -- introspection ---------------------------------------------------------------

    def _default_list_display(self) -> tuple[str, ...]:
        names = [f.name for f in dataclasses.fields(self.model)]
        return tuple(names[:5])

    def model_fields(self) -> list[dataclasses.Field]:
        names = {f.name for f in dataclasses.fields(self.model)}
        editable = [
            f
            for f in dataclasses.fields(self.model)
            if f.name not in ("id", "pk") and f.name not in self.exclude
        ]
        if self.fields:
            order = {name: i for i, name in enumerate(self.fields)}
            editable = [f for f in editable if f.name in order]
            editable.sort(key=lambda f: order[f.name])
            editable = [f for f in editable if f.name in names]
        readonly = set(self.readonly_fields)
        return [f for f in editable if f.name not in readonly]

    def table(self) -> Any:
        pk = getattr(self.model, "pk_name", None)
        return get_table(self.model, pk=pk)

    # -- hooks --------------------------------------------------------------------------

    def get_queryset(self, request: Any) -> list[Any]:
        rows = list(self.table()())
        for key in self.ordering:
            reverse = key.startswith("-")
            field = key.lstrip("-")
            rows.sort(key=lambda r: _sort_value(getattr(r, field, None)), reverse=reverse)
        return rows

    def save_model(self, request: Any, obj: Any, change: bool) -> Any:
        table = self.table()
        if change:
            return table.update(obj)
        return table.insert(**obj)

    def delete_model(self, request: Any, obj: Any) -> None:
        self.table().delete(getattr(obj, "id", None) or getattr(obj, "pk", None))

    def message_user(self, request: Any, message: str, level: str = "success") -> None:
        from ..messages import messages

        getattr(messages, level, messages.info)(request, message)

    # -- permissions ----------------------------------------------------------------------

    def has_permission(self, request: Any, action: str) -> bool:
        user = getattr(request, "user", None) or request.scope.get("user")
        return bool(user is not None and getattr(user, "is_staff", False))


def _sort_value(value: Any) -> Any:
    none_high = (value is None, value if not isinstance(value, bool) else int(value))
    return none_high


class AdminSite:
    """Registry of ModelAdmins plus the namespace where the admin lives."""

    def __init__(self, name: str = "admin") -> None:
        self.name = name
        self._registry: dict[type, ModelAdmin] = {}

    # -- registration -----------------------------------------------------------------

    def register(self, model: type, admin_class: type[ModelAdmin] | None = None, **options: Any) -> None:
        if model in self._registry:
            raise ValueError(f"Model {model.__name__} is already registered.")
        admin = admin_class or ModelAdmin
        instance = admin(model, self)
        for key, value in options.items():
            setattr(instance, key, value)
        self._registry[model] = instance

    def unregister(self, model: type) -> None:
        self._registry.pop(model, None)

    def get_model_admin(self, model: type) -> ModelAdmin:
        try:
            return self._registry[model]
        except KeyError:
            raise KeyError(f"Model {model!r} is not registered.") from None

    def find(self, app_label: str, model_name: str) -> tuple[type, ModelAdmin] | None:
        for model, admin in self._registry.items():
            if model.__name__.lower() == model_name.lower():
                model_app = model.__module__.rsplit(".", 1)[0]
                label = model_app.rsplit(".", 1)[-1]
                if label == app_label:
                    return model, admin
        return None

    # -- queries -------------------------------------------------------------------------

    @property
    def registry(self) -> dict[type, ModelAdmin]:
        return dict(self._registry)

    def by_app(self) -> dict[str, list[tuple[type, ModelAdmin]]]:
        grouped: dict[str, list[tuple[type, ModelAdmin]]] = {}
        for model, admin in self._registry.items():
            label = model.__module__.rsplit(".", 1)[0].rsplit(".", 1)[-1]
            grouped.setdefault(label, []).append((model, admin))
        return grouped


site = AdminSite()


def register(model: type, *, site_obj: AdminSite | None = None) -> Any:
    """Class decorator: ``@register(Product)``."""
    target = site_obj or site

    def decorator(admin_class: type[ModelAdmin]) -> type[ModelAdmin]:
        target.register(model, admin_class)
        return admin_class

    return decorator
