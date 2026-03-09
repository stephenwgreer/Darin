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


def configure_security(app: FastAPI, token: str) -> None:
    """Apply DAR2-34 localhost hardening controls to the FastAPI app.

    Controls applied here:
    - Control 3: Secret token middleware (validates ?token= on all routes)
    - Control 4: Disable FastAPI docs endpoints
    - Control 5: Content-Security-Policy headers

    Controls 1 (127.0.0.1) and 2 (port=0) are set in ui.run() below.
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
    # Generate token once at startup (inside main to avoid module-level side effects)
    _token: str = generate_token()

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
    configure_security(nicegui_app, _token)

    # Open browser with token URL after server starts
    @nicegui_app.on_startup
    async def _open_browser() -> None:
        # NiceGUI/uvicorn binds port=0 to an OS-assigned ephemeral port.
        # We read the actual port from the server's socket after binding.
        # If unavailable, fall back to the configured port.
        port: int = 8080  # fallback
        try:
            # uvicorn stores bound sockets in app.servers after startup
            servers = getattr(nicegui_app, "servers", None)
            if servers and servers[0].sockets:
                socket = servers[0].sockets[0]
                port = socket.getsockname()[1]
        except Exception:  # noqa: BLE001
            pass
        # Token is intentionally passed as a query param — the browser opener
        # cannot set headers. This means the token appears in browser history,
        # which is an accepted trade-off for a localhost-only single-user app.
        webbrowser.open(f"http://127.0.0.1:{port}/?token={_token}")

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
