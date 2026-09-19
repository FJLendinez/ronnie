from fasthtml.common import P, Titled

from ronnie.core.routing import Router

rt = Router("pages")


@rt
def index():
    return Titled("Pages", P("pages index"))


@rt
def about():
    return P("about page")
