import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Audio Settings
BUFFER_MINUTES = 5
SAMPLE_RATE = 48000
CHUNK_SECONDS = 1

# Model Settings
CLAUDE_MODEL = "claude-3-7-sonnet-20250219"
MAX_TOKENS = 1024
TEMPERATURE = 0

# File Settings
TEMP_AUDIO_FILE = "BSGPT_REC.wav"