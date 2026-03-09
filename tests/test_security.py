"""Tests for security token generation (DAR2-34)."""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Add project root to path so that root-level modules are importable,
# consistent with the pattern used by other test modules in this project.
sys.path.insert(0, str(Path(__file__).parent.parent))

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
