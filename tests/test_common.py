"""Tests for ronnie.common — the canonical import surface (derivation)."""

from __future__ import annotations

import subprocess
import sys

import fasthtml.common
import pytest

import ronnie.common as common


class TestDerivation:
    def test_every_public_fasthtml_name_is_available(self):
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
        for name in ("Router", "CsrfToken", "csrf_exempt", "Alerts", "HumanTime", "P"):
            assert name in namespace, name


class TestSingleImportSurfaceE2E:
    """A routes module written entirely against ronnie.common works end-to-end."""

    def test_handler_using_only_ronnie_common(self):
        from starlette.testclient import TestClient

        from ronnie.apps import apps
        from ronnie.conf import settings
        from ronnie.core.asgi import get_asgi_application

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
        with TestClient(get_asgi_application()) as client:
            assert "pages index" in client.get("/pages/").text
            # CSRF helpers imported from common render into a real form page
            page = client.get("/pages/new").text
            assert "csrfmiddlewaretoken" in page
