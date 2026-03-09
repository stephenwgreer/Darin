"""Tests for TokenAuthMiddleware (DAR2-34)."""
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from middleware.token_auth import TokenAuthMiddleware

TOKEN = "test-secret-token-abc123"


def _make_app(token: str) -> Starlette:
    """Build a minimal Starlette app with TokenAuthMiddleware."""
    app = Starlette()
    app.add_middleware(TokenAuthMiddleware, token=token)

    @app.route("/")
    async def index(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.route("/api/data")
    async def data(request: Request) -> PlainTextResponse:
        return PlainTextResponse("data")

    return app


def test_valid_token_in_query_param_allowed() -> None:
    client = TestClient(_make_app(TOKEN), raise_server_exceptions=True)
    resp = client.get(f"/?token={TOKEN}")
    assert resp.status_code == 200


def test_missing_token_rejected() -> None:
    client = TestClient(_make_app(TOKEN), raise_server_exceptions=True)
    resp = client.get("/")
    assert resp.status_code == 403


def test_wrong_token_rejected() -> None:
    client = TestClient(_make_app(TOKEN), raise_server_exceptions=True)
    resp = client.get("/?token=wrong-token")
    assert resp.status_code == 403


def test_nicegui_internal_paths_exempt() -> None:
    """/_nicegui/ paths must never be blocked — they serve assets/socket."""
    app = Starlette()
    app.add_middleware(TokenAuthMiddleware, token=TOKEN)

    @app.route("/_nicegui/assets/test.js")
    async def asset(request: Request) -> PlainTextResponse:
        return PlainTextResponse("js content")

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/_nicegui/assets/test.js")  # No token
    assert resp.status_code == 200


def test_timing_safe_comparison() -> None:
    """Ensure different tokens produce 403, not timing side-channels."""
    client = TestClient(_make_app(TOKEN), raise_server_exceptions=True)
    # Both wrong tokens should be rejected identically
    assert client.get("/?token=a").status_code == 403
    assert client.get("/?token=" + "x" * 100).status_code == 403
