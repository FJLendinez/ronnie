from ronnie.common import P
from ronnie.core.routing import Router

rt = Router("pages")  # deliberately collides with apps.pages


@rt
def index():
    return P("copy index")
