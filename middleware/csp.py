"""Content-Security-Policy middleware for localhost FastAPI server (DAR2-34)."""

from __future__ import annotations

import os

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# script-src is 'self' only: the APP_TOKEN bootstrap moved from an inline
# <script> in index.html to a static .js file, so 'unsafe-inline' is no
# longer required for scripts (LLM output renders in the page — inline
# script execution must stay blocked). style-src keeps 'unsafe-inline'
# because the current CSS relies on inline style attributes.

# Dev-only: the Impeccable live-design helper serves its overlay script and
# SSE/poll endpoints from this origin. Allowed only when DARIN_LIVE_DESIGN=1.
_LIVE_DESIGN_ORIGIN = "http://localhost:8400"


def _build_policy() -> str:
    script_src = "'self'"
    connect_src = "'self'"
    if os.getenv("DARIN_LIVE_DESIGN") == "1":
        script_src += f" {_LIVE_DESIGN_ORIGIN}"
        connect_src += f" {_LIVE_DESIGN_ORIGIN}"
        logger.warning(
            "CSP relaxed for live design mode — remove DARIN_LIVE_DESIGN when done",
            origin=_LIVE_DESIGN_ORIGIN,
        )
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        f"connect-src {connect_src}; "
        "frame-ancestors 'none'"
    )


class CSPMiddleware(BaseHTTPMiddleware):
    """Add Content-Security-Policy header to every response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._policy = _build_policy()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["content-security-policy"] = self._policy
        return response
