"""Content-Security-Policy middleware for localhost FastAPI server (DAR2-34)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


# script-src is 'self' only: the APP_TOKEN bootstrap moved from an inline
# <script> in index.html to a static .js file, so 'unsafe-inline' is no
# longer required for scripts (LLM output renders in the page — inline
# script execution must stay blocked). style-src keeps 'unsafe-inline'
# because the current CSS relies on inline style attributes.
_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
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
