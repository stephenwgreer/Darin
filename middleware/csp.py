"""Content-Security-Policy middleware for localhost NiceGUI server (DAR2-34)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


# NiceGUI injects inline scripts and styles — 'unsafe-inline' is required.
# Acceptable for a localhost-only app with no sensitive data in the browser.
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

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["content-security-policy"] = _CSP_POLICY
        return response
