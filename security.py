"""Security utilities for DAR2-34 localhost hardening."""
from __future__ import annotations

import secrets


def generate_token() -> str:
    """Generate a cryptographically secure URL-safe token.

    Uses 32 bytes of entropy -> ~43 base64url characters.
    Generated once at startup and validated on all HTTP/WebSocket routes.
    """
    return secrets.token_urlsafe(32)
