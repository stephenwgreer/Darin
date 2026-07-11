"""
Tests for API key validation in config.py

Tests that the application properly validates required API keys
on startup and provides clear error messages when keys are missing.

Semantics: passing None for a key means "fall back to the module-level
config value"; passing an empty/whitespace string means "missing".
"""

import sys
from pathlib import Path

import pytest


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import validate_api_keys


def test_validate_api_keys_success() -> None:
    """Test that validation passes when all API keys are present"""
    validate_api_keys(
        anthropic_key="test-anthropic-key",
        deepgram_key="test-deepgram-key",
    )


def test_validate_api_keys_missing_anthropic() -> None:
    """Test that validation fails when Anthropic key is missing"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(anthropic_key="", deepgram_key="test-deepgram-key")

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "Missing required API keys" in error_message
    assert "DEEPGRAM_API_KEY" not in error_message


def test_validate_api_keys_missing_deepgram() -> None:
    """Test that validation fails when Deepgram key is missing"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(anthropic_key="test-anthropic-key", deepgram_key="")

    error_message = str(exc_info.value)
    assert "DEEPGRAM_API_KEY" in error_message
    assert "Missing required API keys" in error_message
    assert "ANTHROPIC_API_KEY" not in error_message


def test_validate_api_keys_missing_both() -> None:
    """Test that validation fails when both keys are missing"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(anthropic_key="", deepgram_key="")

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "DEEPGRAM_API_KEY" in error_message


def test_validate_api_keys_whitespace_only() -> None:
    """Test that validation fails when keys are whitespace-only"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(anthropic_key="   ", deepgram_key="  \t\n  ")

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "DEEPGRAM_API_KEY" in error_message


def test_validate_api_keys_mixed_whitespace() -> None:
    """Test that validation fails when one key is valid and other is whitespace"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(anthropic_key="valid-key", deepgram_key="   ")

    error_message = str(exc_info.value)
    assert "DEEPGRAM_API_KEY" in error_message
    assert "ANTHROPIC_API_KEY" not in error_message


def test_validate_api_keys_with_actual_format() -> None:
    """Test validation with realistic API key formats"""
    validate_api_keys(
        anthropic_key="sk-ant-api03-FAKE-KEY-FOR-TESTING-ONLY-DO-NOT-USE",
        deepgram_key="fake-deepgram-key-32-chars-mock-test",
    )


def test_validate_api_keys_none_falls_back_to_module_config(monkeypatch) -> None:
    """None means 'use module config' — verified with patched module values."""
    import config

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "module-anthropic")
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "module-deepgram")
    validate_api_keys()  # must not raise

    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "")
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys()
    assert "DEEPGRAM_API_KEY" in str(exc_info.value)
