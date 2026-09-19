"""Admin views: generated CRUD over registered tables (FT + HTMX + Pico)."""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

from fasthtml.common import (
    H1,
    H2,
    A,
    Article,
    Button,
    CheckboxX,
    Div,
    Form,
    Head,
    Html,
    Input,
    Label,
    Li,
    Main,
    Meta,
    Nav,
    Ol,
    Option,
    P,
    Select,
    Strong,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
    Ul,
)

from ...conf import settings
from ...core.routing import Router
from ..messages import Alerts
from .site import site

__all__ = ["rt"]

ADMIN_URL = "/admin"  # kept in sync with settings.ADMIN_URL by the app config
rt = Router("admin")


# -- layout -------------------------------------------------------------------------


def _admin_page(req: Any, title: str, *content: Any) -> Any:
    return Html(
        Head(
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            H1(title, style="display:none"),
        ),
        Main(
            Nav(
                Strong(
                    A(
                        str(getattr(settings._wrapped, "ADMIN_SITE_HEADER", None) or "Ronnie Administration"),
                        href="/admin/",
                    )
                ),
                style="padding:.5rem 1rem;background:#181c24;color:#fff",
            ),
            Div(Alerts(req), style="padding:0 1rem"),
            Div(*content, style="padding:0 1rem"),
            cls="container",
        ),
    )


def _csrf(req: Any) -> Any:
    from ...middleware.csrf import CsrfToken

    return CsrfToken(req)


def _require_staff(req: Any) -> Any:
    """Redirect to login unless the user is staff; None means OK."""
    user = req.scope.get("user")
    if user is not None and getattr(user, "is_staff", False):
        return None
    from fasthtml.common import Redirect

    return Redirect(f"/accounts/login?next={req.url.path}")


def _resolve(app_label: str, model_name: str) -> tuple[type, Any] | None:
    return site.find(app_label, model_name)


# -- index --------------------------------------------------------------------------


@rt
def index(req):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    sections = []
    for label, entries in sorted(site.by_app().items()):
        sections.append(
            Article(
                H2(label.title()),
                Ul(
                    *[
                        Li(
                            A(
                                f"{model.__name__}",
                                href=f"/admin/{label}/{model.__name__.lower()}",
                            )
                        )
                        for model, _admin in entries
                    ]
                ),
            )
        )
    return (
        _admin_page(req, "Admin", *sections)
        if sections
        else _admin_page(req, "Admin", P("Nothing registered yet."))
    )


# -- changelist ------------------------------------------------------------------------


def _sort_arrow(params: dict, column: str, admin: Any) -> str:
    if column in admin.list_filter:
        return ""
    if params.get("o") == column:
        return "↓ "
    if params.get("o") == f"-{column}":
        return "↑ "
    return ""


def _cell(admin: Any, row: Any, name: str) -> Any:
    value = getattr(row, name, None)
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if value is None or value == "":
        return admin.empty_value_display
    return str(value)


@rt("/{app_label}/{model_name}")
def changelist(req, app_label: str, model_name: str):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    found = _resolve(app_label, model_name)
    if found is None:
        return _admin_page(req, "Admin", P("Unknown model."))
    _model, admin = found

    rows = admin.get_queryset(req)
    params = dict(req.query_params)
    query = params.get("q", "").strip().lower()
    if query and admin.search_fields:
        rows = [
            r for r in rows if any(query in str(getattr(r, f, "") or "").lower() for f in admin.search_fields)
        ]
    filter_field = params.get("f", "")
    filter_value = params.get("v", "")
    if filter_field and filter_value and filter_field in admin.list_filter:
        rows = [r for r in rows if str(getattr(r, filter_field, "")) == filter_value]
    order_by = params.get("o", "")
    if order_by:
        reverse = order_by.startswith("-")
        key = order_by.lstrip("-")
        rows = sorted(
            rows,
            key=lambda r, k=key: (getattr(r, k, None) is None, getattr(r, k, None)),
            reverse=reverse,
        )
    try:
        page = max(1, int(params.get("page", 1)))
    except ValueError:
        page = 1
    per_page = admin.list_per_page
    total = len(rows)
    rows_page = rows[(page - 1) * per_page : page * per_page]

    base = f"/admin/{app_label}/{model_name}"
    columns = admin.list_display or tuple(f.name for f in dataclasses.fields(_model))

    header = Tr(
        *[
            Th(
                A(
                    (
                        ""
                        if c in admin.list_filter
                        else ("↓ " if params.get("o") == c else ("↑ " if params.get("o") == f"-{c}" else ""))
                    )
                    + c.replace("_", " ").title(),
                    href=f"{base}?o={'-' + c if params.get('o') == c else c}"
                    + (f"&q={query}" if query else ""),
                )
            )
            for c in columns
        ],
        Th(""),
    )

    def row_tr(row: Any) -> Tr:
        pk = getattr(row, "id", None) or getattr(row, "pk", None)
        cells = []
        for i, column in enumerate(columns):
            cell = _cell(admin, row, column)
            if i == 0:
                cells.append(Td(A(str(cell), href=f"{base}/{pk}/change")))
            else:
                cells.append(Td(cell))
        cells.append(
            Td(
                A("🗑", href=f"{base}/{pk}/delete", title="Delete"),
                style="text-align:right",
            )
        )
        return Tr(
            Td(CheckboxX(name=f"sel-{pk}", cls="row-select", value=str(pk))),
            *cells,
        )

    body_rows = [row_tr(r) for r in rows_page] or [Tr(Td("No rows.", colspan=len(columns) + 2))]

    filter_panel = ""
    if admin.list_filter:
        links = [Strong("Filters")]
        for field in admin.list_filter:
            values = sorted({str(getattr(r, field, "")) for r in rows} - {""})
            for value in values[:12]:
                links.append(
                    Li(
                        A(
                            f"{field.replace('_', ' ').title()}: {value}",
                            href=f"{base}?f={field}&v={value}",
                        )
                    )
                )
        filter_panel = Article(H2("Filters"), Ul(*links[1:]), style="max-width:220px")

    search_box = ""
    if admin.search_fields:
        search_box = Input(
            type="search",
            name="q",
            value=query,
            placeholder="Search…",
            hx_get=base,
            hx_trigger="keyup changed delay:300ms",
            hx_target="body",
        )

    nav = Ol(
        *[
            Li(A(str(n), href=f"{base}?page={n}" + (f"&q={query}" if query else "")))
            for n in range(max(1, page - 2), min((total // per_page) + 2, page + 3))
            if n >= 1
        ],
        style="display:flex;gap:.5rem;list-style:none",
    )

    return _admin_page(
        req,
        f"{_model.__name__} list",
        H1(f"{_model.__name__}s"),
        A(f"+ Add {_model.__name__}", href=f"{base}/add"),
        Div(search_box) if search_box else "",
        Form(
            _csrf(req),
            Table(Thead(header), Tbody(*body_rows)),
            Select(
                Option("Action…", value=""),
                Option("Delete selected", value="delete_selected"),
                name="action",
            ),
            Button("Run", type="submit"),
            action=f"{base}/action",
            method="post",
        ),
        P(f"{total} row(s) — page {page}") if total else "",
        nav if total > per_page else "",
        filter_panel,
    )


# -- forms -----------------------------------------------------------------------------

_WIDGETS = {
    int: lambda f, v: Input(type="number", name=f.name, value="" if v is None else v),
    float: lambda f, v: Input(type="number", step="any", name=f.name, value="" if v is None else v),
    bool: lambda f, v: CheckboxX(name=f.name, checked=bool(v)),
    dt.date: lambda f, v: Input(type="date", name=f.name, value=str(v or "")),
    dt.datetime: lambda f, v: Input(type="datetime-local", name=f.name, value=str(v or "")),
}


def _widget_for(field: Any, value: Any) -> Any:
    annotation = field.type if isinstance(field.type, type) else str
    for known, builder in _WIDGETS.items():
        if annotation is known or str(annotation) == known.__name__:
            return builder(field, value)
    if str(annotation).startswith("int"):
        return _WIDGETS[int](field, value)
    if str(annotation).startswith("float"):
        return _WIDGETS[float](field, value)
    if str(annotation).startswith("bool"):
        return _WIDGETS[bool](field, value)
    return Input(name=field.name, value="" if value is None else value)


def _object_form(
    req: Any, base: str, admin: Any, model: type, instance: Any = None, verb: str = "Add"
) -> Any:
    from ...middleware.csrf import CsrfToken

    fields = admin.model_fields()
    widgets = []
    for field in fields:
        current = getattr(instance, field.name, None) if instance else None
        default = (
            current
            if current is not None
            else (field.default if field.default is not dataclasses.MISSING else "")
        )
        widgets.append(Div(Label(field.name.replace("_", " ").title()), _widget_for(field, default)))
    return Form(
        CsrfToken(req),
        *widgets,
        Button(f"{verb} {model.__name__}", type="submit"),
        action=(
            f"{base}/{getattr(instance, 'id', getattr(instance, 'pk', None))}/change"
            if instance
            else f"{base}/add"
        ),
        method="post",
    )


def _coerce(field: Any, raw: Any) -> Any:
    annotation = str(field.type)
    if raw is None:
        return None
    text = str(raw)
    if annotation.startswith("bool"):
        return text in ("on", "true", "1", "True")
    if annotation.startswith("int"):
        return int(text) if text else None
    if annotation.startswith("float"):
        return float(text) if text else None
    return text


@rt("/{app_label}/{model_name}/add")
def get(req, app_label: str, model_name: str):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    found = _resolve(app_label, model_name)
    if found is None:
        return P("Unknown model.")
    model, admin = found
    return _admin_page(
        req,
        f"Add {model.__name__}",
        H1(f"Add {model.__name__}"),
        _object_form(req, f"/admin/{app_label}/{model_name}", admin, model),
    )


@rt("/{app_label}/{model_name}/{pk}/change")
def get(req, app_label: str, model_name: str, pk: str):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    found = _resolve(app_label, model_name)
    if found is None:
        return P("Unknown model.")
    model, admin = found
    if not pk:
        pk = dict(req.query_params).get("pk", "")
    try:
        instance = admin.table()[int(pk)]
    except Exception:
        return P("Object not found.")
    return _admin_page(
        req,
        f"Change {model.__name__}",
        H1(f"Change {model.__name__}"),
        _object_form(req, f"/admin/{app_label}/{model_name}", admin, model, instance=instance, verb="Change"),
        A("Delete", href=f"/admin/{app_label}/{model_name}/{pk}/delete"),
    )


# -- mutations ---------------------------------------------------------------------------


@rt("/{app_label}/{model_name}/add")
def post(req, app_label: str, model_name: str, data: dict):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    found = _resolve(app_label, model_name)
    if found is None:
        return P("Unknown model.")
    model, admin = found
    values = {}
    for field in admin.model_fields():
        if field.name in (data or {}):
            values[field.name] = _coerce(field, data[field.name])
        elif str(field.type).startswith("bool"):
            values[field.name] = False
    admin.save_model(req, values, change=False)
    admin.message_user(req, f"{model.__name__} added.")
    from fasthtml.common import Redirect

    return Redirect(f"/admin/{app_label}/{model_name}")


@rt("/{app_label}/{model_name}/{pk}/change")
def post(req, app_label: str, model_name: str, pk: str, data: dict):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    found = _resolve(app_label, model_name)
    if found is None:
        return P("Unknown model.")
    model, admin = found
    try:
        instance = admin.table()[int(pk)]
    except Exception:
        return P("Object not found.")
    for field in admin.model_fields():
        if field.name in (data or {}):
            setattr(instance, field.name, _coerce(field, data[field.name]))
    admin.save_model(req, instance, change=True)
    admin.message_user(req, f"{model.__name__} updated.")
    from fasthtml.common import Redirect

    return Redirect(f"/admin/{app_label}/{model_name}")


@rt("/{app_label}/{model_name}/{pk}/delete")
def delete_view(req, app_label: str, model_name: str, pk: str):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    found = _resolve(app_label, model_name)
    if found is None:
        return P("Unknown model.")
    model, admin = found
    try:
        instance = admin.table()[int(pk)]
    except Exception:
        return P("Object not found.")
    admin.delete_model(req, instance)
    admin.message_user(req, f"{model.__name__} deleted.", level="warning")
    from fasthtml.common import Redirect

    return Redirect(f"/admin/{app_label}/{model_name}")


@rt("/{app_label}/{model_name}/action")
def post(req, app_label: str, model_name: str, data: dict):
    guard = _require_staff(req)
    if guard is not None:
        return guard
    found = _resolve(app_label, model_name)
    if found is None:
        return P("Unknown model.")
    model, admin = found
    action = (data or {}).get("action", "")
    ids = [v for k, v in (data or {}).items() if k.startswith("sel-")]
    if action == "delete_selected" and ids:
        table = admin.table()
        for object_id in ids:
            table.delete(int(object_id))
        admin.message_user(req, f"Deleted {len(ids)} {model.__name__}(s).", level="warning")
    from fasthtml.common import Redirect

    return Redirect(f"/admin/{app_label}/{model_name}")
