"""Configuration module for Darin Audio Assistant.

Loads environment variables and provides validated API keys.
All configuration values are defined here as the single source of truth.
"""

import os
from typing import Final

from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

# API Keys (loaded from environment)
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
DEEPGRAM_API_KEY: str | None = os.getenv("DEEPGRAM_API_KEY")

# Audio Settings
# Internal capture format: int16, 16 kHz, 100 ms chunks (1600 frames),
# shape (1600, 2) — column 0 = ME (default mic), column 1 = THEM (speaker loopback).
BUFFER_MINUTES: Final[int] = 5
SAMPLE_RATE: Final[int] = 16000
CHUNK_SECONDS: Final[float] = 0.1
# Fallback capture rate when a device refuses 16 kHz (decimated 3:1 to 16 kHz).
FALLBACK_SAMPLE_RATE: Final[int] = 48000

# Deepgram Streaming Settings
DEEPGRAM_MODEL: Final[str] = "nova-3"
DEEPGRAM_LANGUAGE: Final[str] = "en-US"
DEEPGRAM_SAMPLE_RATE: Final[int] = 16000
# Domain vocabulary boosted via nova-3 keyterm prompting (user-editable later
# via AppConfig; empty list = no boosting).
DEEPGRAM_KEYTERMS: Final[list[str]] = []

# Model tiers (verified live 2026-07-10 — both IDs resolve on the Anthropic API).
# WATCHER_MODEL: proactive watcher ticks, titles, rolling summary, map-reduce.
# REACTIVE_MODEL: the 5 reactive card buttons + freeform Ask.
# POST_MEETING_MODEL: long-form post-meeting analyses.
WATCHER_MODEL: Final[str] = "claude-haiku-4-5"
REACTIVE_MODEL: Final[str] = "claude-sonnet-5"
POST_MEETING_MODEL: Final[str] = "claude-sonnet-5"

# Per-lane defaults. Temperature is never sent (removed on current models).
WATCHER_MAX_TOKENS: Final[int] = 500
REACTIVE_MAX_TOKENS: Final[int] = 400
ASK_MAX_TOKENS: Final[int] = 600
POST_MEETING_MAX_TOKENS: Final[int] = 4096
TITLE_MAX_TOKENS: Final[int] = 64

# Watcher lane client: fail fast, never queue retries behind a live meeting.
WATCHER_TIMEOUT_S: Final[float] = 8.0
WATCHER_MAX_RETRIES: Final[int] = 0

# OpenAI-compatible provider client (custom endpoints): mirror the Anthropic
# lane retry/timeout posture. Watcher lane = fail fast; everything else uses the
# SDK defaults (2 retries, 10-min timeout).
OPENAI_COMPAT_WATCHER_TIMEOUT_S: Final[float] = 8.0
OPENAI_COMPAT_WATCHER_MAX_RETRIES: Final[int] = 0

# Anthropic server-side web-search tool (F3). Verified live 2026-07-11 against
# anthropic-sdk 0.78.0: claude-sonnet-5 accepts BOTH the dynamic-filtering
# `web_search_20260209` variant (which actually searched) and the basic
# `web_search_20250305`. The 20260209 variant requires an Opus-4.6+/Sonnet-4.6+
# class model; Haiku falls back to the basic variant.
ANTHROPIC_WEB_SEARCH_TOOL_TYPE: Final[str] = "web_search_20260209"
ANTHROPIC_WEB_SEARCH_TOOL_TYPE_BASIC: Final[str] = "web_search_20250305"
ANTHROPIC_WEB_SEARCH_MAX_USES: Final[int] = 4

# Background lane: rolling summary cadence (~every 5 min of meeting time).
ROLLING_SUMMARY_INTERVAL_S: Final[float] = 300.0
ROLLING_SUMMARY_MAX_TOKENS: Final[int] = 400

# Context pack budget (estimated as len(text.split()) * 1.3).
CONTEXT_PACK_MAX_TOKENS: Final[int] = 20_000


def validate_api_keys(
    *,
    anthropic_key: str | None = None,
    deepgram_key: str | None = None,
) -> None:
    """
    Validate that required API keys are present and non-empty.

    Args:
        anthropic_key: Explicit key to validate; None means "use module config".
        deepgram_key: Explicit key to validate; None means "use module config".

    Raises:
        EnvironmentError: If any required API keys are missing or empty.

    Note:
        Keys are validated for both presence and non-whitespace content.
        Empty strings and whitespace-only strings are treated as missing.

    Examples:
        >>> # Production usage (uses module config)
        >>> validate_api_keys()

        >>> # Test missing keys
        >>> validate_api_keys(anthropic_key="", deepgram_key="")
        ... # Raises EnvironmentError

        >>> # Test with explicit keys
        >>> validate_api_keys(anthropic_key="test-key", deepgram_key="test-key")
        ... # Passes validation
    """
    api_key_anthropic = ANTHROPIC_API_KEY if anthropic_key is None else anthropic_key
    api_key_deepgram = DEEPGRAM_API_KEY if deepgram_key is None else deepgram_key

    missing_keys: list[str] = []

    # Check for missing, empty, or whitespace-only keys
    if not api_key_anthropic or (
        isinstance(api_key_anthropic, str) and not api_key_anthropic.strip()
    ):
        missing_keys.append("ANTHROPIC_API_KEY")
    if not api_key_deepgram or (isinstance(api_key_deepgram, str) and not api_key_deepgram.strip()):
        missing_keys.append("DEEPGRAM_API_KEY")

    if missing_keys:
        error_msg = (
            "Missing required API keys:\n\n"
            + "\n".join(f"  - {key}" for key in missing_keys)
            + "\n\nPlease set these in your .env file or environment variables."
        )
        raise OSError(error_msg)
