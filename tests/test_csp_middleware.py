"""Tests for CSPMiddleware (DAR2-34)."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from middleware.csp import CSPMiddleware


def _make_app() -> Starlette:
    app = Starlette()
    app.add_middleware(CSPMiddleware)

    @app.route("/")
    async def index(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app


def test_csp_header_present() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=True)
    resp = client.get("/")
    assert "content-security-policy" in resp.headers


def test_csp_allows_self() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=True)
    csp = client.get("/").headers["content-security-policy"]
    assert "'self'" in csp


def test_csp_blocks_frame_embedding() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=True)
    csp = client.get("/").headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp


def test_csp_allows_self_connect() -> None:
    """connect-src 'self' covers SSE (HTTP); ws:/wss: removed (no WebSocket used)."""
    client = TestClient(_make_app(), raise_server_exceptions=True)
    csp = client.get("/").headers["content-security-policy"]
    assert "connect-src" in csp
    assert "'self'" in csp


def test_csp_script_src_disallows_unsafe_inline() -> None:
    """LLM output renders in the page — inline script execution must stay blocked.

    The APP_TOKEN bootstrap moved to a static .js file, so script-src is
    'self' only. style-src keeps 'unsafe-inline' (current CSS needs it).
    """
    client = TestClient(_make_app(), raise_server_exceptions=True)
    csp = client.get("/").headers["content-security-policy"]
    directives = {d.strip().split(" ")[0]: d.strip() for d in csp.split(";") if d.strip()}
    assert directives["script-src"] == "script-src 'self'"
    assert "'unsafe-inline'" not in directives["script-src"]


def test_csp_applied_to_all_responses() -> None:
    app = Starlette()
    app.add_middleware(CSPMiddleware)

    @app.route("/page")
    async def page(request: Request) -> PlainTextResponse:
        return PlainTextResponse("page")

    @app.route("/api")
    async def api(request: Request) -> PlainTextResponse:
        return PlainTextResponse("api")

    client = TestClient(app, raise_server_exceptions=True)
    assert "content-security-policy" in client.get("/page").headers
    assert "content-security-policy" in client.get("/api").headers
