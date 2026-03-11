"""Entry point for Darin Audio Assistant (vanilla JS + FastAPI).

Starts a uvicorn server on 127.0.0.1 with an OS-assigned ephemeral port,
then opens the browser with the one-time auth token in the URL.

Usage:
    uv run python main.py
"""

from __future__ import annotations

import asyncio
import webbrowser

import uvicorn

from security import generate_token
from web.app import create_app


async def _serve() -> None:
    """Create the app, start uvicorn on port=0, open the browser."""
    token = generate_token()
    fastapi_app = create_app(token)

    # port=0 lets the OS assign a free ephemeral port (Control 2 of DAR2-34)
    config = uvicorn.Config(
        app=fastapi_app,
        host="127.0.0.1",
        port=0,
        log_level="info",
        reload=False,
    )
    server = uvicorn.Server(config)

    # Start uvicorn in the background so we can read the bound port
    serve_task = asyncio.create_task(server.serve())

    # Wait until uvicorn has bound its socket
    while not server.started:
        await asyncio.sleep(0.05)

    # Discover the OS-assigned port from the listening socket
    port: int = 8080  # fallback (should never be needed)
    try:
        port = server.servers[0].sockets[0].getsockname()[1]
    except Exception:  # noqa: BLE001
        pass

    # Open browser with token — intentionally in URL (localhost-only, single user)
    webbrowser.open(f"http://127.0.0.1:{port}/?token={token}")

    await serve_task


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
