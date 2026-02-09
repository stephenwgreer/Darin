"""
Tests for API key validation in config.py

Tests that the application properly validates required API keys
on startup and provides clear error messages when keys are missing.
"""

import os
import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_validate_api_keys_success(monkeypatch):
    """Test that validation passes when all API keys are present"""
    # Set up environment with valid keys
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-deepgram-key")

    # Reload config to pick up new environment variables
    import importlib
    import config
    importlib.reload(config)

    # Should not raise
    config.validate_api_keys()


def test_validate_api_keys_missing_anthropic(monkeypatch):
    """Test that validation fails with clear message when Anthropic key is missing"""
    # Remove Anthropic key, keep Deepgram
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-deepgram-key")

    # Reload config
    import importlib
    import config
    importlib.reload(config)

    # Should raise EnvironmentError with specific key mentioned
    with pytest.raises(EnvironmentError) as exc_info:
        config.validate_api_keys()

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "Missing required API keys" in error_message


def test_validate_api_keys_missing_deepgram(monkeypatch):
    """Test that validation fails when Deepgram key is missing"""
    # Keep Anthropic, remove Deepgram
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

    # Reload config
    import importlib
    import config
    importlib.reload(config)

    # Should raise EnvironmentError with specific key mentioned
    with pytest.raises(EnvironmentError) as exc_info:
        config.validate_api_keys()

    error_message = str(exc_info.value)
    assert "DEEPGRAM_API_KEY" in error_message
    assert "Missing required API keys" in error_message


def test_validate_api_keys_missing_both(monkeypatch):
    """Test that validation fails when both keys are missing"""
    # Remove both keys
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

    # Reload config
    import importlib
    import config
    importlib.reload(config)

    # Should raise EnvironmentError mentioning both keys
    with pytest.raises(EnvironmentError) as exc_info:
        config.validate_api_keys()

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "DEEPGRAM_API_KEY" in error_message
    assert "Missing required API keys" in error_message


def test_validate_api_keys_empty_string(monkeypatch):
    """Test that validation fails when keys are empty strings"""
    # Set keys to empty strings (which are falsy)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "")

    # Reload config
    import importlib
    import config
    importlib.reload(config)

    # Should raise EnvironmentError
    with pytest.raises(EnvironmentError) as exc_info:
        config.validate_api_keys()

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "DEEPGRAM_API_KEY" in error_message


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
