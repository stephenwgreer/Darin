"""Content-Security-Policy middleware for localhost FastAPI server (DAR2-34)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


# unsafe-inline in script-src is kept for the small APP_TOKEN bootstrap
# script injected inline in index.html.  unsafe-eval and ws:/wss: are no
# longer needed (removed Vue.js / WebSocket dependency).
_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
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
