"""Content-Security-Policy middleware for localhost NiceGUI server (DAR2-34)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


# NiceGUI injects inline scripts/styles. Vue.js requires the unsafe-eval
# CSP directive (a browser security policy string, not Python eval).
# font-src needs data: for NiceGUI's inline base64 woff2 fonts.
# All acceptable for a localhost-only app with no sensitive data in the browser.
_SCRIPT_SRC = "'self' 'unsafe-inline' 'unsafe-eval'"  # Vue.js runtime requirement
_CSP_POLICY = (
    "default-src 'self'; "
    f"script-src {_SCRIPT_SRC}; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
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
