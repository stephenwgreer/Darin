from __future__ import annotations

import pytest

import config
from prompts.templates import (
    REACTIVE_SYSTEM_PROMPT,
    WATCHER_SYSTEM_PROMPT,
    build_watcher_system,
)


@pytest.mark.unit
def test_watcher_prompt_carries_user_name_aliases() -> None:
    """A question addressing ME by name must be recognizable — every alias
    spelling has to reach the watcher's system prompt."""
    for alias in config.USER_NAME_ALIASES:
        assert alias in WATCHER_SYSTEM_PROMPT


@pytest.mark.unit
def test_watcher_prompt_name_present_for_all_personas() -> None:
    for persona in ("general", "sales", "technical"):
        prompt = build_watcher_system(persona)
        for alias in config.USER_NAME_ALIASES:
            assert alias in prompt


@pytest.mark.unit
def test_reactive_prompt_carries_user_name_aliases() -> None:
    for alias in config.USER_NAME_ALIASES:
        assert alias in REACTIVE_SYSTEM_PROMPT


@pytest.mark.unit
def test_user_name_is_boosted_keyterm() -> None:
    """The name must be in Deepgram keyterms so it transcribes reliably."""
    assert config.USER_NAME in config.DEEPGRAM_KEYTERMS
