import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


def validate_api_keys():
    """
    Validate that required API keys are present and non-empty.

    Raises:
        EnvironmentError: If any required API keys are missing or empty.
    """
    missing_keys = []

    if not ANTHROPIC_API_KEY:
        missing_keys.append("ANTHROPIC_API_KEY")
    if not DEEPGRAM_API_KEY:
        missing_keys.append("DEEPGRAM_API_KEY")

    if missing_keys:
        error_msg = (
            "Missing required API keys:\n\n"
            + "\n".join(f"  - {key}" for key in missing_keys)
            + "\n\nPlease set these in your .env file or environment variables."
        )
        raise EnvironmentError(error_msg)

# Audio Settings
BUFFER_MINUTES = 5
SAMPLE_RATE = 48000
CHUNK_SECONDS = 1

# Model Settings
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 4096
TEMPERATURE = 0

# File Settings
TEMP_AUDIO_FILE = "BSGPT_REC.wav"