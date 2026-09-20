"""Tests for Ronnie's import surfaces: curated `ronnie.common` + per-module mirrors."""

from __future__ import annotations

import importlib
import pkgutil
import subprocess
import sys

import fasthtml
import fasthtml.common
import pytest

import ronnie.common as common


def importable_fasthtml_submodules() -> list[str]:
    names = []
    for info in pkgutil.iter_modules(fasthtml.__path__):
        if info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"fasthtml.{info.name}")
        except ImportError:
            continue
        names.append(info.name)
    return names


class TestModuleMirrors:
    def test_mirror_exists_for_every_submodule(self):
        for name in importable_fasthtml_submodules():
            assert importlib.import_module(f"ronnie.{name}") is not None

    def test_every_public_name_of_every_submodule(self):
        missing: dict[str, list[str]] = {}
        for name in importable_fasthtml_submodules():
            source = importlib.import_module(f"fasthtml.{name}")
            mirror = importlib.import_module(f"ronnie.{name}")
            gaps = [n for n in dir(source) if not n.startswith("_") and not hasattr(mirror, n)]
            if gaps:
                missing[name] = gaps
        assert missing == {}, missing

    def test_lazy_names_resolve_through_mirrors(self):
        # The source resolves some names via PEP 562 (not in dir()); the
        # mirrors must resolve them too.
        components = importlib.import_module("ronnie.components")
        for name in ("Titled", "Form", "P", "Main"):
            assert hasattr(components, name), name

    def test_core_mirror_has_engine_names(self):
        from ronnie.core import APIRouter, FastHTML, to_xml

        assert callable(FastHTML) and callable(to_xml) and callable(APIRouter)

    def test_core_mirror_keeps_ronnie_submodules(self):
        from ronnie.core import asgi, checks, management, routing, signals  # noqa: F401

    def test_svg_mirror_renders(self):
        from ronnie.core import to_xml
        from ronnie.svg import Circle, Rect, Svg

        xml = to_xml(Svg(Rect(width=10, height=10)))
        assert xml.strip().startswith("<svg")
        assert "<circle" in to_xml(Svg(Circle(r=5)))

    def test_pico_mirror_renders(self):
        from ronnie.core import to_xml
        from ronnie.pico import Card

        assert to_xml(Card("hi")).strip().startswith("<article")

    def test_oauth_and_helpers_mirrors(self):
        from ronnie.jupyter import JupyUvi, nb_serve  # noqa: F401
        from ronnie.live_reload import LiveReloadJs  # noqa: F401
        from ronnie.oauth import GitHubAppClient, OAuth, consent_url  # noqa: F401
        from ronnie.xtend import Urlset, use_kwargs  # noqa: F401

    def test_optional_mirror_degrades_gracefully(self):
        mirror = importlib.import_module("ronnie.stripe_otp")
        try:
            importlib.import_module("fasthtml.stripe_otp")
        except ImportError:
            assert mirror.__all__ == []
        else:
            assert mirror.__all__ != []

    def test_star_import_from_mirror(self):
        namespace: dict = {}
        exec("from ronnie.svg import *", namespace)
        assert "Circle" in namespace and "Svg" in namespace


class TestCuratedCommon:
    def test_common_parity_with_source_common(self):
        missing = [
            name for name in dir(fasthtml.common) if not name.startswith("_") and not hasattr(common, name)
        ]
        assert missing == []

    def test_common_is_curated_not_a_dump(self):
        # Module-specific vocabularies live in their mirrors, not in common.
        for name in ("Card", "Grid", "DialogX", "Circle", "Rect", "GitHubAppClient", "Urlset", "JupyUvi"):
            assert not hasattr(common, name), name
        # Svg comes from the XML core and is legitimately part of the
        # curated surface — parity beats assumptions.
        assert hasattr(common, "Svg")

    def test_everyday_names(self):
        for name in (
            "FastHTML",
            "fast_app",
            "serve",
            "Redirect",
            "Titled",
            "P",
            "Form",
            "Hidden",
            "HttpHeader",
            "to_xml",
            "APIRouter",
            "Beforeware",
            "RedirectResponse",
            "Response",
            "Request",
            "Middleware",
            "StaticFiles",
            "dataclass",
        ):
            assert hasattr(common, name), name

    def test_components_render(self):
        assert common.to_xml(common.P("x")).strip() == "<p>x</p>"
        assert "<title>" in common.to_xml(common.Titled("T", common.P("b")))

    def test_all_lists_everything(self):
        for name in common.__all__:
            assert hasattr(common, name), name

    def test_unknown_attribute_raises(self):
        with pytest.raises(AttributeError, match="no attribute 'nope'"):
            _ = common.nope


class TestRonnieExports:
    def test_router_is_ronnies_not_starlettes(self):
        import starlette.routing

        from ronnie.core.routing import Router

        assert common.Router is Router
        assert common.Router is not starlette.routing.Router

    def test_csrf_helpers(self):
        from ronnie.middleware.csrf import (
            CsrfToken,
            csrf_exempt,
            csrf_token,
            hx_csrf_headers,
        )

        assert common.CsrfToken is CsrfToken
        assert common.csrf_token is csrf_token
        assert common.csrf_exempt is csrf_exempt
        assert common.hx_csrf_headers is hx_csrf_headers

    def test_alerts_and_humantime(self):
        from ronnie.contrib.humanize import HumanTime
        from ronnie.contrib.messages import Alerts

        assert common.Alerts is Alerts
        assert common.HumanTime is HumanTime

    def test_common_import_pulls_no_contrib_at_load_time(self):
        code = (
            "import sys, ronnie.common; "
            "assert 'ronnie.contrib.messages' not in sys.modules, 'contrib loaded'; "
            "assert 'ronnie.middleware.csrf' not in sys.modules, 'middleware loaded'; "
            "from ronnie.common import CsrfToken; "
            "assert 'ronnie.middleware.csrf' in sys.modules; "
            "print('OK')"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        assert "OK" in result.stdout

    def test_star_import_resolves_lazy_names(self):
        namespace: dict = {}
        exec("from ronnie.common import *", namespace)
        for name in ("Router", "CsrfToken", "csrf_exempt", "Alerts", "HumanTime", "P"):
            assert name in namespace, name


class TestSingleImportSurfaceE2E:
    def test_handler_using_only_ronnie_imports(self):
        from starlette.testclient import TestClient

        from ronnie.apps import apps
        from ronnie.conf import settings

        settings.configure(
            SECRET_KEY="k",
            DEBUG=False,
            ALLOWED_HOSTS=["testserver"],
            INSTALLED_APPS=["apps.pages"],
            MIDDLEWARE=[],
        )
        apps.clear_data()
        import ronnie

        ronnie.setup()
        from ronnie.core.asgi import get_asgi_application

        with TestClient(get_asgi_application()) as client:
            assert "pages index" in client.get("/pages/").text
            page = client.get("/pages/new").text
            assert "csrfmiddlewaretoken" in page

    def test_svg_route_via_mirror(self, monkeypatch):
        import sys
        import types

        from starlette.testclient import TestClient

        from ronnie.apps import apps
        from ronnie.common import Router
        from ronnie.conf import settings
        from ronnie.svg import Circle, Svg

        graphics = Router("graphics")

        @graphics("/badge")  # explicit path: nested handlers have test qualnames
        def badge():
            return Svg(Circle(r=5))

        module = types.ModuleType("apps.graphics.routes")
        module.rt = graphics
        graphics_pkg = types.ModuleType("apps.graphics")
        monkeypatch.setitem(sys.modules, "apps.graphics", graphics_pkg)
        monkeypatch.setitem(sys.modules, "apps.graphics.routes", module)

        settings.configure(
            SECRET_KEY="k",
            DEBUG=False,
            ALLOWED_HOSTS=["testserver"],
            INSTALLED_APPS=["apps.pages", "apps.graphics"],
            MIDDLEWARE=[],
        )
        apps.clear_data()
        import ronnie

        ronnie.setup()
        from ronnie.core.asgi import get_asgi_application

        with TestClient(get_asgi_application()) as client:
            body = client.get("/graphics/badge").text
            assert "<svg" in body and "<circle" in body

    def test_pico_component_in_real_page(self):
        # The login page uses Card from the pico mirror.
        from starlette.testclient import TestClient

        from ronnie.apps import apps
        from ronnie.conf import settings

        settings.configure(
            SECRET_KEY="k",
            DEBUG=False,
            ALLOWED_HOSTS=["testserver"],
            INSTALLED_APPS=["apps.pages", "ronnie.contrib.sessions", "ronnie.contrib.auth"],
            MIDDLEWARE=[
                "ronnie.middleware.host.HostValidationMiddleware",
                "ronnie.contrib.sessions.middleware.SessionMiddleware",
                "ronnie.middleware.csrf.CsrfMiddleware",
            ],
        )
        apps.clear_data()
        import ronnie

        ronnie.setup()
        from ronnie.core.asgi import get_asgi_application

        with TestClient(get_asgi_application()) as client:
            assert "<article" in client.get("/accounts/login").text
