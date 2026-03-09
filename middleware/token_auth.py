"""Token authentication middleware for localhost NiceGUI server (DAR2-34)."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
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
        if not token:
            raise ValueError("TokenAuthMiddleware requires a non-empty token")
        self._token = token

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Exempt NiceGUI internals
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Validate token via timing-safe comparison
        provided = request.query_params.get("token", "")
        if not hmac.compare_digest(
            provided.encode("utf-8", errors="replace"), self._token.encode()
        ):
            return PlainTextResponse("Forbidden", status_code=403)

        return await call_next(request)
