"""
Configuration for Darin Audio Assistant
FastAPI Backend Configuration with Environment Variables
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# FastAPI Server Settings
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

# Audio Settings
BUFFER_MINUTES = int(os.getenv("BUFFER_MINUTES", "3"))  # Reduced from 5 to 3 for performance
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "48000"))
CHUNK_SECONDS = int(os.getenv("CHUNK_SECONDS", "1"))

# AI Model Settings
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))

# File Settings
TEMP_AUDIO_FILE = os.getenv("TEMP_AUDIO_FILE", "BSGPT_REC.wav")
FRONTEND_DIST_PATH = Path(os.getenv("FRONTEND_DIST_PATH", "frontend/dist"))

# WebSocket Settings
WS_PING_INTERVAL = int(os.getenv("WS_PING_INTERVAL", "30"))  # seconds
WS_PING_TIMEOUT = int(os.getenv("WS_PING_TIMEOUT", "10"))   # seconds

# Development Settings
AUTO_OPEN_BROWSER = os.getenv("AUTO_OPEN_BROWSER", "true").lower() == "true"
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Performance Settings
MAX_CONCURRENT_ANALYSES = int(os.getenv("MAX_CONCURRENT_ANALYSES", "3"))
AUDIO_CLEANUP_INTERVAL = int(os.getenv("AUDIO_CLEANUP_INTERVAL", "300"))  # seconds

# Validation
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY not set in environment variables")
    
    if not DEEPGRAM_API_KEY:
        errors.append("DEEPGRAM_API_KEY not set in environment variables")
    
    if BUFFER_MINUTES < 1 or BUFFER_MINUTES > 10:
        errors.append(f"BUFFER_MINUTES should be 1-10, got {BUFFER_MINUTES}")
    
    if MAX_TOKENS < 100 or MAX_TOKENS > 8000:
        errors.append(f"MAX_TOKENS should be 100-8000, got {MAX_TOKENS}")
    
    return errors

def print_config_status():
    """Print configuration status for debugging"""
    print("📋 Configuration Status:")
    print(f"   Anthropic API: {'✅ Configured' if ANTHROPIC_API_KEY else '❌ Missing'}")
    print(f"   Deepgram API:  {'✅ Configured' if DEEPGRAM_API_KEY else '❌ Missing'}")
    print(f"   Server:        {SERVER_HOST}:{SERVER_PORT}")
    print(f"   Audio Buffer:  {BUFFER_MINUTES} minutes @ {SAMPLE_RATE}Hz")
    print(f"   Claude Model:  {CLAUDE_MODEL}")
    print(f"   Frontend:      {'✅ Available' if FRONTEND_DIST_PATH.exists() else '❌ Not built'}")
    
    # Validation
    validation_errors = validate_config()
    if validation_errors:
        print("⚠️  Configuration Issues:")
        for error in validation_errors:
            print(f"   - {error}")
    else:
        print("✅ Configuration Valid")

# Export main settings for easy import
__all__ = [
    "ANTHROPIC_API_KEY", "DEEPGRAM_API_KEY",
    "SERVER_HOST", "SERVER_PORT", "LOG_LEVEL",
    "BUFFER_MINUTES", "SAMPLE_RATE", "CHUNK_SECONDS",
    "CLAUDE_MODEL", "MAX_TOKENS", "TEMPERATURE",
    "TEMP_AUDIO_FILE", "FRONTEND_DIST_PATH",
    "AUTO_OPEN_BROWSER", "DEBUG_MODE",
    "validate_config", "print_config_status"
]