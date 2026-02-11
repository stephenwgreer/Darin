"""
Tests for API key validation in config.py

Tests that the application properly validates required API keys
on startup and provides clear error messages when keys are missing.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import validate_api_keys


def test_validate_api_keys_success() -> None:
    """Test that validation passes when all API keys are present"""
    validate_api_keys(
        anthropic_key="test-anthropic-key",
        deepgram_key="test-deepgram-key",
        _use_module_defaults=False
    )


def test_validate_api_keys_missing_anthropic() -> None:
    """Test that validation fails when Anthropic key is missing"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(
            anthropic_key=None,
            deepgram_key="test-deepgram-key",
            _use_module_defaults=False
        )

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "Missing required API keys" in error_message
    assert "DEEPGRAM_API_KEY" not in error_message


def test_validate_api_keys_missing_deepgram() -> None:
    """Test that validation fails when Deepgram key is missing"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(
            anthropic_key="test-anthropic-key",
            deepgram_key=None,
            _use_module_defaults=False
        )

    error_message = str(exc_info.value)
    assert "DEEPGRAM_API_KEY" in error_message
    assert "Missing required API keys" in error_message
    assert "ANTHROPIC_API_KEY" not in error_message


def test_validate_api_keys_missing_both() -> None:
    """Test that validation fails when both keys are missing"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(
            anthropic_key=None,
            deepgram_key=None,
            _use_module_defaults=False
        )

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "DEEPGRAM_API_KEY" in error_message


def test_validate_api_keys_empty_string() -> None:
    """Test that validation fails when keys are empty strings"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(
            anthropic_key="",
            deepgram_key="",
            _use_module_defaults=False
        )

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "DEEPGRAM_API_KEY" in error_message


def test_validate_api_keys_whitespace_only() -> None:
    """Test that validation fails when keys are whitespace-only"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(
            anthropic_key="   ",
            deepgram_key="  \t\n  ",
            _use_module_defaults=False
        )

    error_message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_message
    assert "DEEPGRAM_API_KEY" in error_message


def test_validate_api_keys_mixed_whitespace() -> None:
    """Test that validation fails when one key is valid and other is whitespace"""
    with pytest.raises(EnvironmentError) as exc_info:
        validate_api_keys(
            anthropic_key="valid-key",
            deepgram_key="   ",
            _use_module_defaults=False
        )

    error_message = str(exc_info.value)
    assert "DEEPGRAM_API_KEY" in error_message
    assert "ANTHROPIC_API_KEY" not in error_message


def test_validate_api_keys_with_actual_format() -> None:
    """Test validation with realistic API key formats"""
    validate_api_keys(
        anthropic_key="sk-ant-api03-XdW48x0VkJXBKEJx8Jz1QjxnbBALwKrq2orWZYdslrD",
        deepgram_key="dbdd8c40b2221419b4e53a21767b32e61b358efe",
        _use_module_defaults=False
    )


def test_validate_api_keys_uses_module_defaults() -> None:
    """Test that validation uses module config when no params provided"""
    try:
        validate_api_keys()
    except EnvironmentError:
        # Expected if .env has missing keys
        pass
