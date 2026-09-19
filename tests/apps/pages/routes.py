from fasthtml.common import Button, Form, Input, P, Titled

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


@rt
def new(req):
    from ronnie.middleware.csrf import CsrfToken

    return Form(
        CsrfToken(req),
        Input(name="title"),
        Button("Save"),
        action="/pages/save",
        method="post",
    )


@rt
def save(title: str = ""):
    return P(f"saved:{title}")


@rt
def counter(sess):
    sess["n"] = sess.get("n", 0) + 1
    return P(f"count:{sess['n']}")
