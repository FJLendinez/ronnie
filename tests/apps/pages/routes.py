from fasthtml.common import Button, Form, Input, P, Titled

from ronnie.contrib.auth.decorators import login_required
from ronnie.core.routing import Router
from ronnie.middleware.csrf import csrf_exempt

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


@rt
def profile(req):
    return P("public-profile")


@rt
@login_required
def protected(req):
    return P("protected-content")


@rt
def flash_save(req):
    from fasthtml.common import Redirect

    from ronnie.contrib.messages import messages

    messages.success(req, "Saved!")
    messages.info(req, "FYI", extra_tags="banner")
    return Redirect("/pages/flash_show")


@rt
def flash_show(req):
    from ronnie.contrib.messages import Alerts

    return Alerts(req)


@rt
@csrf_exempt
def webhook(req):
    return P("webhook-ok")


@rt("/hook/{token}")
@csrf_exempt
def hook(req, token: str):
    return P(f"hook-{token}")


@rt
def guarded_post(req):
    return P("guarded-ok")
