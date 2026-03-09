"""Tests verifying security controls are wired correctly (DAR2-34)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI


# Add project root to path so that root-level modules are importable,
# consistent with the pattern used by other test modules in this project.
sys.path.insert(0, str(Path(__file__).parent.parent))

from main_nicegui import configure_security
from middleware.csp import CSPMiddleware
from middleware.token_auth import TokenAuthMiddleware


def test_configure_security_disables_docs() -> None:
    app = FastAPI()
    configure_security(app, "test-token-abc123")
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


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
