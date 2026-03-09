# DAR2-34: Localhost Security Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the NiceGUI localhost server with a secret-token auth middleware, CSP headers middleware, and disabled FastAPI docs endpoints.

**Architecture:** Two Starlette `BaseHTTPMiddleware` classes (`TokenAuthMiddleware`, `CSPMiddleware`) registered on `ui.app` before `ui.run()`. A `generate_token()` helper in `security.py` creates a `secrets.token_urlsafe(32)` token at startup. The two controls already implemented (`host="127.0.0.1"`, `port=0`) are confirmed and documented but need no code changes.

**Tech Stack:** Python 3.11, NiceGUI ≥3.0 (FastAPI/Starlette under the hood), `secrets` stdlib, `hmac` stdlib, `starlette.middleware.base.BaseHTTPMiddleware`, `pytest`, `ruff`, `mypy --strict`

---

## Pre-flight: Confirm existing controls pass

Before writing new code, verify the two already-implemented controls are correct.

**Step 1: Read `main_nicegui.py` and confirm**

Open `/mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign/main_nicegui.py`.

Confirm these lines exist:
```python
ui.run(
    host="127.0.0.1",   # Control 1 ✓
    port=0,             # Control 2 ✓
    ...
)
```

Both are already in place. No code change needed for controls 1 and 2.

---

## Task 1: `security.py` — token generation helper

**Files:**
- Create: `security.py`
- Test: `tests/test_security.py`

### Step 1: Write the failing test

Create `tests/test_security.py`:

```python
"""Tests for security token generation (DAR2-34)."""
from __future__ import annotations

import re

from security import generate_token


def test_generate_token_returns_string() -> None:
    token = generate_token()
    assert isinstance(token, str)


def test_generate_token_minimum_length() -> None:
    # token_urlsafe(32) produces ~43 base64url characters
    token = generate_token()
    assert len(token) >= 40


def test_generate_token_url_safe_characters() -> None:
    token = generate_token()
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", token), f"Not URL-safe: {token!r}"


def test_generate_token_unique() -> None:
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100, "Tokens should be unique"
```

### Step 2: Run test to verify it fails

```bash
cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign
uv run pytest tests/test_security.py -v
```

Expected: `ModuleNotFoundError: No module named 'security'`

### Step 3: Write minimal implementation

Create `security.py`:

```python
"""Security utilities for DAR2-34 localhost hardening."""
from __future__ import annotations

import secrets


def generate_token() -> str:
    """Generate a cryptographically secure URL-safe token.

    Uses 32 bytes of entropy → ~43 base64url characters.
    Generated once at startup and validated on all HTTP/WebSocket routes.
    """
    return secrets.token_urlsafe(32)
```

### Step 4: Run test to verify it passes

```bash
uv run pytest tests/test_security.py -v
```

Expected: 4 passed

### Step 5: Commit

```bash
git add security.py tests/test_security.py
git commit -m "feat(DAR2-34): add token generation helper"
```

---

## Task 2: `middleware/token_auth.py` — secret token middleware

**Files:**
- Create: `middleware/__init__.py` (empty)
- Create: `middleware/token_auth.py`
- Test: `tests/test_token_auth_middleware.py`

**Context:** NiceGUI wraps FastAPI/Starlette. `ui.app` is the underlying `FastAPI` instance. Middleware is added via `ui.app.add_middleware(...)` or `ui.app.middleware("http")(...)`. We use `BaseHTTPMiddleware` from starlette for simplicity.

**Token delivery:** The token is embedded in the URL as a query parameter (`?token=...`) when NiceGUI opens the browser. All subsequent NiceGUI socket.io WebSocket frames use the same origin connection — we exempt WebSocket upgrade requests and NiceGUI's internal `/_nicegui/` paths to avoid breaking the UI framework internals.

**Exempt paths** (must not block):
- `/_nicegui/` — NiceGUI static assets and socket.io endpoint
- `/` with valid token on first load

### Step 1: Write the failing tests

Create `tests/test_token_auth_middleware.py`:

```python
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
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/test_token_auth_middleware.py -v
```

Expected: `ModuleNotFoundError: No module named 'middleware'`

### Step 3: Write minimal implementation

Create `middleware/__init__.py` (empty file).

Create `middleware/token_auth.py`:

```python
"""Token authentication middleware for localhost NiceGUI server (DAR2-34)."""
from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp

# NiceGUI internal paths that must never be blocked.
# These serve static assets, socket.io, and framework internals.
_EXEMPT_PREFIXES = ("/_nicegui/",)


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Validate a shared secret on every HTTP request.

    The token is passed as a query parameter: `?token=<value>`.
    NiceGUI-internal paths are exempt to avoid breaking the framework.
    Comparison uses hmac.compare_digest to prevent timing attacks.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: object) -> Response:
        path = request.url.path

        # Exempt NiceGUI internals
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)  # type: ignore[operator]

        # Validate token via timing-safe comparison
        provided = request.query_params.get("token", "")
        if not hmac.compare_digest(provided, self._token):
            return PlainTextResponse("Forbidden", status_code=403)

        return await call_next(request)  # type: ignore[operator]
```

### Step 4: Run test to verify it passes

```bash
uv run pytest tests/test_token_auth_middleware.py -v
```

Expected: 5 passed

### Step 5: Run ruff and mypy

```bash
uv run ruff check middleware/token_auth.py
uv run mypy middleware/token_auth.py --strict
```

Expected: no errors

### Step 6: Commit

```bash
git add middleware/__init__.py middleware/token_auth.py tests/test_token_auth_middleware.py
git commit -m "feat(DAR2-34): add token auth middleware"
```

---

## Task 3: `middleware/csp.py` — Content-Security-Policy headers

**Files:**
- Create: `middleware/csp.py`
- Test: `tests/test_csp_middleware.py`

**Context:** NiceGUI uses socket.io (WebSocket + long-polling), serves inline scripts, and loads assets from the same origin. The CSP must allow:
- `'self'` for scripts, styles, images, fonts, connect-src
- `'unsafe-inline'` for scripts and styles (NiceGUI injects inline JS/CSS — unavoidable)
- `ws:` and `wss:` for `connect-src` (socket.io WebSocket)
- `frame-ancestors 'none'` — no embedding in iframes

### Step 1: Write the failing tests

Create `tests/test_csp_middleware.py`:

```python
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


def test_csp_allows_websocket_connect() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=True)
    csp = client.get("/").headers["content-security-policy"]
    assert "connect-src" in csp
    assert "ws:" in csp


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
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/test_csp_middleware.py -v
```

Expected: `ModuleNotFoundError: No module named 'middleware.csp'`

### Step 3: Write minimal implementation

Create `middleware/csp.py`:

```python
"""Content-Security-Policy middleware for localhost NiceGUI server (DAR2-34)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# NiceGUI injects inline scripts and styles — 'unsafe-inline' is required.
# This is acceptable for a localhost-only app with no sensitive data in the browser.
_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'none'"
)


class CSPMiddleware(BaseHTTPMiddleware):
    """Add Content-Security-Policy header to every response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["content-security-policy"] = _CSP_POLICY
        return response
```

### Step 4: Run test to verify it passes

```bash
uv run pytest tests/test_csp_middleware.py -v
```

Expected: 5 passed

### Step 5: Run ruff and mypy

```bash
uv run ruff check middleware/csp.py
uv run mypy middleware/csp.py --strict
```

Expected: no errors

### Step 6: Commit

```bash
git add middleware/csp.py tests/test_csp_middleware.py
git commit -m "feat(DAR2-34): add CSP header middleware"
```

---

## Task 4: Disable FastAPI docs + wire everything into `main_nicegui.py`

**Files:**
- Modify: `main_nicegui.py`
- Test: `tests/test_main_security.py`

**Context:** NiceGUI's `ui.app` is a standard `FastAPI` instance. FastAPI docs (`/docs`, `/redoc`, `/openapi.json`) are enabled by default. They must be disabled in production. Middleware is registered on `ui.app` before `ui.run()`.

**Token URL injection:** After calling `ui.run()`, NiceGUI opens the browser automatically (`show=True`). We need to pass the token in the URL. NiceGUI accepts a custom `favicon_path` but not a custom launch URL. We override the browser-open behavior by setting `show=False` and calling `webbrowser.open(f"http://127.0.0.1:{port}/?token={token}")` ourselves after the server starts — but NiceGUI's `port=0` means we don't know the port until after startup.

**Simpler approach:** Use NiceGUI's `on_startup` hook with `app.on_startup` to open the browser after the server binds, reading the actual port from `ui.server`. Check NiceGUI docs for the actual API — the key is: don't open browser before port is known.

**Actually the simplest approach for this app:** Since `port=0` is already set and NiceGUI handles browser opening via `show=True`, we use NiceGUI's `app.on_startup` async hook to register the middleware and open the browser with the token URL. Use `show=False` and open the browser manually.

NiceGUI startup sequence:
1. `ui.run()` called → binds socket, assigns port
2. `app.on_startup` hooks fire (async, server is ready)
3. Browser can be opened here with known port + token

Implementation in `main_nicegui.py`:

```python
import webbrowser
from nicegui import app as nicegui_app, ui
from security import generate_token
from middleware.token_auth import TokenAuthMiddleware
from middleware.csp import CSPMiddleware

TOKEN = generate_token()

# Disable FastAPI docs before ui.run()
nicegui_app.docs_url = None      # disables /docs
nicegui_app.redoc_url = None     # disables /redoc
nicegui_app.openapi_url = None   # disables /openapi.json

# Register middleware
nicegui_app.add_middleware(TokenAuthMiddleware, token=TOKEN)
nicegui_app.add_middleware(CSPMiddleware)

@nicegui_app.on_startup
async def open_browser() -> None:
    port = ui.run_kwargs.get("port")  # or read from server
    webbrowser.open(f"http://127.0.0.1:{port}/?token={TOKEN}")

ui.run(show=False, host="127.0.0.1", port=0, ...)
```

**Note:** Verify the exact NiceGUI API for reading the bound port. Check `nicegui` source or docs for `ui.run_kwargs`, `app.native.main_window`, or similar. If `port=0` OS assignment isn't exposed, fall back to a fixed high port (e.g., 18542) for now and document the limitation.

### Step 1: Write the failing tests

Create `tests/test_main_security.py`:

```python
"""Tests verifying security controls are wired in main_nicegui (DAR2-34)."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def test_token_auth_middleware_registered() -> None:
    """TokenAuthMiddleware must be added to ui.app before ui.run."""
    from middleware.token_auth import TokenAuthMiddleware

    mock_app = MagicMock()
    with (
        patch("main_nicegui.nicegui_app", mock_app),
        patch("main_nicegui.ui") as mock_ui,
        patch("main_nicegui.AppController"),
        patch("main_nicegui.MeetingStore"),
        patch("main_nicegui.config"),
        patch("main_nicegui.create_meeting_page"),
    ):
        import importlib
        import main_nicegui
        importlib.reload(main_nicegui)

    calls = [str(c) for c in mock_app.add_middleware.call_args_list]
    assert any("TokenAuthMiddleware" in c for c in calls)


def test_csp_middleware_registered() -> None:
    """CSPMiddleware must be added to ui.app before ui.run."""
    from middleware.csp import CSPMiddleware

    mock_app = MagicMock()
    with (
        patch("main_nicegui.nicegui_app", mock_app),
        patch("main_nicegui.ui"),
        patch("main_nicegui.AppController"),
        patch("main_nicegui.MeetingStore"),
        patch("main_nicegui.config"),
        patch("main_nicegui.create_meeting_page"),
    ):
        import importlib
        import main_nicegui
        importlib.reload(main_nicegui)

    calls = [str(c) for c in mock_app.add_middleware.call_args_list]
    assert any("CSPMiddleware" in c for c in calls)


def test_docs_disabled() -> None:
    """FastAPI docs endpoints must be disabled."""
    mock_app = MagicMock()
    with (
        patch("main_nicegui.nicegui_app", mock_app),
        patch("main_nicegui.ui"),
        patch("main_nicegui.AppController"),
        patch("main_nicegui.MeetingStore"),
        patch("main_nicegui.config"),
        patch("main_nicegui.create_meeting_page"),
    ):
        import importlib
        import main_nicegui
        importlib.reload(main_nicegui)

    assert mock_app.docs_url is None
    assert mock_app.redoc_url is None
    assert mock_app.openapi_url is None
```

**Note:** These tests are tricky because `main_nicegui` runs side effects on import. If the tests are too brittle due to reload complexity, use a simpler integration approach: extract a `configure_security(app)` function and test that directly.

**Simpler alternative test approach** — extract and test `configure_security`:

In `main_nicegui.py`, extract:
```python
def configure_security(app: FastAPI, token: str) -> None:
    app.docs_url = None
    app.redoc_url = None
    app.openapi_url = None
    app.add_middleware(TokenAuthMiddleware, token=token)
    app.add_middleware(CSPMiddleware)
```

Then test:
```python
def test_configure_security_disables_docs() -> None:
    from fastapi import FastAPI
    from main_nicegui import configure_security
    app = FastAPI()
    configure_security(app, "test-token")
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

def test_configure_security_adds_middleware() -> None:
    from fastapi import FastAPI
    from main_nicegui import configure_security
    from middleware.token_auth import TokenAuthMiddleware
    from middleware.csp import CSPMiddleware
    app = FastAPI()
    configure_security(app, "test-token")
    middleware_types = [m.cls for m in app.user_middleware]
    assert TokenAuthMiddleware in middleware_types
    assert CSPMiddleware in middleware_types
```

**Use whichever approach runs cleanly.** The extracted `configure_security` approach is strongly preferred.

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/test_main_security.py -v
```

Expected: `ImportError` or `AttributeError`

### Step 3: Rewrite `main_nicegui.py` with security wiring

```python
"""NiceGUI entry point for Darin Audio Assistant (DAR2-26).

Separate from the existing PyQt6 main.py (HoE decision: keep both
during transition, retire main.py when PyQt6 UI is fully removed).

Usage:
    uv run python main_nicegui.py
"""

from __future__ import annotations

import webbrowser

from fastapi import FastAPI
from nicegui import app as nicegui_app
from nicegui import ui

import config
from app_controller import AppController
from middleware.csp import CSPMiddleware
from middleware.token_auth import TokenAuthMiddleware
from security import generate_token
from storage.meeting_store import MeetingStore
from ui.pages.meeting_page import create_meeting_page

# --- Security: generate token once at startup ---
_TOKEN: str = generate_token()


def configure_security(app: FastAPI, token: str) -> None:
    """Apply all DAR2-34 localhost hardening controls to the FastAPI app.

    Controls applied here:
    - Control 3: Secret token middleware (validates ?token= on all routes)
    - Control 4: Disable FastAPI docs endpoints
    - Control 5: Content-Security-Policy headers

    Controls 1 (127.0.0.1) and 2 (port=0) are applied in ui.run() call below.
    """
    # Control 4: Disable docs
    app.docs_url = None
    app.redoc_url = None
    app.openapi_url = None

    # Control 3: Token auth on all routes
    app.add_middleware(TokenAuthMiddleware, token=token)

    # Control 5: CSP headers on all responses
    app.add_middleware(CSPMiddleware)


def main() -> None:
    """Initialize AppController and start NiceGUI server."""
    # Validate API keys
    config.validate_api_keys()

    # Initialize backend
    controller = AppController()
    controller.meeting_store = MeetingStore()

    # Start continuous recording (circular buffer always running)
    controller.start_recording()

    # Register NiceGUI pages
    create_meeting_page(controller)

    # Apply security hardening to NiceGUI's underlying FastAPI app
    configure_security(nicegui_app, _TOKEN)

    # Open browser manually with token in URL after server starts
    @nicegui_app.on_startup
    async def _open_browser() -> None:
        # NiceGUI stores the bound port after startup
        # Access via the server's socket binding
        try:
            port = ui.run_kwargs["port"]  # type: ignore[index]
        except (KeyError, TypeError):
            port = 8080  # fallback
        webbrowser.open(f"http://127.0.0.1:{port}/?token={_TOKEN}")

    # Start NiceGUI server on localhost
    # Control 1: host="127.0.0.1" — never 0.0.0.0
    # Control 2: port=0 — OS assigns random ephemeral port
    ui.run(
        title="Darin Audio Assistant",
        host="127.0.0.1",
        port=0,  # Random ephemeral port (Control 2)
        show=False,  # We open browser manually with token URL
        reload=False,
    )


if __name__ == "__main__":
    main()
```

**Important:** After writing this, run the app manually to verify the browser opens with the token URL. The `ui.run_kwargs["port"]` may or may not reflect the OS-assigned port — test and adjust if needed. If it doesn't work, check NiceGUI's `app.native` or look for the actual bound port in NiceGUI's internals.

### Step 4: Run tests to verify they pass

```bash
uv run pytest tests/test_main_security.py -v
```

Expected: all pass

### Step 5: Run full test suite

```bash
uv run pytest tests/ -v --ignore=tests/ui -x
```

Expected: all existing tests still pass (no regressions)

### Step 6: Ruff + mypy

```bash
uv run ruff check main_nicegui.py middleware/ security.py
uv run mypy main_nicegui.py middleware/ security.py --strict
```

Expected: no errors

### Step 7: Commit

```bash
git add main_nicegui.py tests/test_main_security.py
git commit -m "feat(DAR2-34): wire security hardening into main_nicegui"
```

---

## Task 5: Final verification

### Step 1: Run full test suite

```bash
uv run pytest tests/ --ignore=tests/ui -v
```

Expected: all new tests pass, no regressions in existing tests

### Step 2: Verify acceptance criteria checklist

Go through each AC from the Linear issue:

- [ ] **Control 1** — `ui.run(host="127.0.0.1", ...)` confirmed in `main_nicegui.py`
- [ ] **Control 2** — `ui.run(port=0, ...)` confirmed in `main_nicegui.py`
- [ ] **Control 3** — `TokenAuthMiddleware` registered, `?token=` validated, `hmac.compare_digest` used
- [ ] **Control 4** — `docs_url=None`, `redoc_url=None`, `openapi_url=None` set
- [ ] **Control 5** — `CSPMiddleware` registered, `content-security-policy` header on all responses

### Step 3: Final commit and push

```bash
git add -A
git commit -m "feat(DAR2-34): localhost security hardening complete"
```

Push from Windows PowerShell (authentication works there).

---

## Summary of New Files

| File | Purpose |
|------|---------|
| `security.py` | `generate_token()` helper |
| `middleware/__init__.py` | Package marker |
| `middleware/token_auth.py` | Token auth middleware |
| `middleware/csp.py` | CSP header middleware |
| `tests/test_security.py` | Token generation tests |
| `tests/test_token_auth_middleware.py` | Token auth middleware tests |
| `tests/test_csp_middleware.py` | CSP middleware tests |
| `tests/test_main_security.py` | Integration: wiring tests |

## Modified Files

| File | Change |
|------|--------|
| `main_nicegui.py` | Add `configure_security()`, register middleware, manual browser open |
