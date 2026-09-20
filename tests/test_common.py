"""Tests for ronnie.common — the canonical import surface (full derivation)."""

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
    """Every fasthtml submodule that imports cleanly (minus internals)."""
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


class TestFullPackageDerivation:
    def test_every_public_name_of_every_submodule(self):
        missing: dict[str, list[str]] = {}
        for name in importable_fasthtml_submodules():
            module = importlib.import_module(f"fasthtml.{name}")
            gaps = [n for n in dir(module) if not n.startswith("_") and not hasattr(common, n)]
            if gaps:
                missing[name] = gaps
        assert missing == {}, missing

    def test_derived_submodules_matches_importable_set(self):
        expected = {"common", *importable_fasthtml_submodules()}
        assert set(common.derived_submodules()) == expected

    def test_svg_components_render(self):
        xml = common.to_xml(common.Svg(common.Rect(width=10, height=10)))
        assert xml.strip().startswith("<svg")

    def test_pico_components_render(self):
        xml = common.to_xml(common.Card(common.P("hi")))
        assert xml.strip().startswith("<article")

    def test_core_re_exports(self):
        # Names that live in fasthtml.core but not in the curated common list.
        for name in ("UUID", "Callable", "NAMESPACE_URL", "add_route"):
            assert hasattr(common, name), name

    def test_spot_check_each_extra_submodule(self):
        spot = {
            "svg": ("Circle", "Rect", "Svg"),
            "pico": ("Card", "Container", "DialogX", "Grid", "Group"),
            "xtend": ("Urlset", "Url", "use_kwargs"),
            "oauth": ("OAuth", "GitHubAppClient", "GoogleAppClient", "consent_url"),
            "live_reload": ("LiveReloadJs", "live_reload_ws"),
            "jupyter": ("JupyUvi", "nb_serve"),
            "cli": ("railway_deploy", "call_parse"),
        }
        for names in spot.values():
            for name in names:
                assert hasattr(common, name), name

    def test_optional_submodule_gracefully_skipped(self):
        try:
            importlib.import_module("fasthtml.stripe_otp")
        except ImportError:
            assert "stripe_otp" not in common.derived_submodules()
        else:
            assert "stripe_otp" in common.derived_submodules()

    def test_common_names_precedence(self):
        # The curated surface wins over later submodules.
        assert common.Redirect is fasthtml.common.Redirect


class TestDerivationBasics:
    def test_every_public_fasthtml_common_name_is_available(self):
        missing = [
            name for name in dir(fasthtml.common) if not name.startswith("_") and not hasattr(common, name)
        ]
        assert missing == []

    def test_core_names(self):
        for name in (
            "FastHTML",
            "fast_app",
            "serve",
            "Redirect",
            "Titled",
            "P",
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
        ):
            assert hasattr(common, name), name

    def test_components_render(self):
        assert common.to_xml(common.P("x")).strip() == "<p>x</p>"
        assert "<title>" in common.to_xml(common.Titled("T", common.P("b")))

    def test_all_lists_everything(self):
        for name in common.__all__:
            assert hasattr(common, name), name

    def test_dir_includes_lazy_names(self):
        listing = dir(common)
        for name in ("CsrfToken", "csrf_exempt", "Alerts", "HumanTime", "Router"):
            assert name in listing

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

    def test_lazy_import_does_not_pull_contrib_at_import_time(self):
        # A fresh interpreter importing ronnie.common must not import contrib apps.
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
        for name in ("Router", "CsrfToken", "csrf_exempt", "Alerts", "HumanTime", "P", "Card"):
            assert name in namespace, name


class TestSingleImportSurfaceE2E:
    """A routes module written entirely against ronnie.common works end-to-end."""

    def test_handler_using_only_ronnie_common(self):
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
            # CSRF helpers imported from common render into a real form page
            page = client.get("/pages/new").text
            assert "csrfmiddlewaretoken" in page

    def test_svg_route_via_common(self, monkeypatch):
        import sys
        import types

        from starlette.testclient import TestClient

        from ronnie.apps import apps
        from ronnie.common import Circle, Svg
        from ronnie.conf import settings
        from ronnie.core.routing import Router

        graphics = Router("graphics")

        @graphics("/badge")  # explicit path: nested handlers have test qualnames
        def badge():
            return Svg(Circle(r=5))

        graphics_module = types.ModuleType("apps.graphics.routes")
        graphics_module.rt = graphics
        graphics_pkg = types.ModuleType("apps.graphics")
        monkeypatch.setitem(sys.modules, "apps.graphics", graphics_pkg)
        monkeypatch.setitem(sys.modules, "apps.graphics.routes", graphics_module)

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
