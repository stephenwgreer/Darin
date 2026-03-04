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
BUFFER_MINUTES: Final[int] = 5
SAMPLE_RATE: Final[int] = 48000
CHUNK_SECONDS: Final[int] = 1

# Deepgram Streaming Settings
DEEPGRAM_MODEL: Final[str] = "nova-2"
DEEPGRAM_LANGUAGE: Final[str] = "en-US"
DEEPGRAM_SAMPLE_RATE: Final[int] = 48000

# Model Settings
CLAUDE_MODEL: Final[str] = "claude-sonnet-4-5-20250929"
MAX_TOKENS: Final[int] = 4096
TEMPERATURE: Final[int] = 0

# File Settings
TEMP_AUDIO_FILE: Final[str] = "BSGPT_REC.wav"


def validate_api_keys(
    *,
    anthropic_key: str | None = None,
    deepgram_key: str | None = None,
    _use_module_defaults: bool = True,
) -> None:
    """
    Validate that required API keys are present and non-empty.

    Args:
        anthropic_key: Anthropic API key override for testing.
                      If None and _use_module_defaults=False, treated as missing.
        deepgram_key: Deepgram API key override for testing.
                     If None and _use_module_defaults=False, treated as missing.
        _use_module_defaults: If True, use module-level config when keys are None.
                             If False, None means missing (for testing).

    Raises:
        EnvironmentError: If any required API keys are missing or empty.

    Note:
        Keys are validated for both presence and non-whitespace content.
        Empty strings and whitespace-only strings are treated as missing.

    Examples:
        >>> # Production usage (uses module config)
        >>> validate_api_keys()

        >>> # Test missing keys
        >>> validate_api_keys(anthropic_key=None, deepgram_key=None, _use_module_defaults=False)
        ... # Raises EnvironmentError

        >>> # Test with explicit keys
        >>> validate_api_keys(anthropic_key="test-key", deepgram_key="test-key", _use_module_defaults=False)
        ... # Passes validation
    """
    # Determine which keys to validate
    if _use_module_defaults:
        # Production mode: use module config if parameters are None
        api_key_anthropic = anthropic_key if anthropic_key is not None else ANTHROPIC_API_KEY
        api_key_deepgram = deepgram_key if deepgram_key is not None else DEEPGRAM_API_KEY
    else:
        # Test mode: use provided values directly (None means missing)
        api_key_anthropic = anthropic_key
        api_key_deepgram = deepgram_key

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
