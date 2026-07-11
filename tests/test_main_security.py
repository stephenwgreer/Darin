"""Tests verifying security controls are wired correctly (DAR2-34)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from middleware.csp import CSPMiddleware
from middleware.token_auth import TokenAuthMiddleware
from web.app import build_fastapi_app, configure_security


def test_build_fastapi_app_disables_docs() -> None:
    """Docs must be disabled at CONSTRUCTION time (Control 4).

    Assigning docs_url after FastAPI() is a no-op because the docs routes
    are registered inside FastAPI.__init__ — the old bug this guards against.
    """
    app = build_fastapi_app()
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_docs_routes_return_404() -> None:
    """The docs/openapi routes must not exist on the constructed app."""
    from starlette.testclient import TestClient

    app = build_fastapi_app()
    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_configure_security_registers_token_auth_middleware() -> None:
    app = FastAPI()
    configure_security(app, "test-token-abc123")
    middleware_types = [m.cls for m in app.user_middleware]
    assert TokenAuthMiddleware in middleware_types


def test_configure_security_registers_csp_middleware() -> None:
    app = FastAPI()
    configure_security(app, "test-token-abc123")
    middleware_types = [m.cls for m in app.user_middleware]
    assert CSPMiddleware in middleware_types


def test_configure_security_rejects_empty_token() -> None:
    """Empty token must be rejected — guard is in TokenAuthMiddleware.__init__.

    FastAPI/Starlette defers middleware construction until the first request,
    so we must send a request via TestClient to trigger instantiation.
    """
    from starlette.testclient import TestClient

    app = FastAPI()
    configure_security(app, "")
    # Trigger middleware instantiation — Starlette is lazy
    with pytest.raises(ValueError, match="non-empty token"):
        TestClient(app).get("/")
