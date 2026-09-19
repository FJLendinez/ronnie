from fasthtml.common import P, Titled

from ronnie.core.routing import Router

rt = Router("pages")


@rt
def index():
    return Titled("Pages", P("pages index"))


@rt
def about():
    return P("about page")


@rt
def echo_htmx(req):
    return P("is-htmx" if req.headers.get("hx-request") else "not-htmx")


@rt
def go():
    from fasthtml.common import Redirect

    return Redirect("/pages/")
