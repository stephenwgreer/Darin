# tests/test_prompt_registry_effective.py
import pytest

import config
from prompts.registry import ASK_PROMPT_CONFIG, get_effective_registry, get_prompt_config_by_id
from storage.app_config import AppConfig, CustomPromptConfig


@pytest.mark.unit
def test_effective_registry_returns_all_builtins_by_default():
    cfg = AppConfig()
    registry = get_effective_registry(cfg)
    ids = [p.id for p in registry]
    assert "answer_this" in ids
    assert "fact_check" in ids
    assert "meeting_summary" in ids


@pytest.mark.unit
def test_effective_registry_excludes_deleted_ids():
    cfg = AppConfig(deleted_prompt_ids=["fact_check"])
    registry = get_effective_registry(cfg)
    ids = [p.id for p in registry]
    assert "fact_check" not in ids
    assert "answer_this" in ids


@pytest.mark.unit
def test_effective_registry_applies_overrides():
    cfg = AppConfig(prompt_overrides={"answer_this": {"button_text": "My Answer"}})
    registry = get_effective_registry(cfg)
    p = next(p for p in registry if p.id == "answer_this")
    assert p.button_text == "My Answer"


@pytest.mark.unit
def test_effective_registry_appends_custom_prompts():
    cfg = AppConfig(
        custom_prompts=[
            CustomPromptConfig(id="cp_foo", button_text="Foo", output_title="Foo Out", template="t")
        ]
    )
    registry = get_effective_registry(cfg)
    ids = [p.id for p in registry]
    assert "cp_foo" in ids
    p = next(p for p in registry if p.id == "cp_foo")
    assert p.bucket == "custom"


@pytest.mark.unit
def test_custom_prompts_are_reactive_style():
    """Custom prompts run through the reactive card lane."""
    cfg = AppConfig(
        custom_prompts=[
            CustomPromptConfig(
                id="cp_bar", button_text="Bar", output_title="Bar Out", template="tmpl"
            )
        ]
    )
    registry = get_effective_registry(cfg)
    p = next(p for p in registry if p.id == "cp_bar")
    assert p.template == "tmpl"
    assert p.template_type == "card"
    assert p.model == config.REACTIVE_MODEL
    assert p.max_tokens > 0


@pytest.mark.unit
def test_prompt_configs_carry_model_and_max_tokens():
    """PromptConfig gained model + max_tokens fields (per-lane tiers)."""
    reactive = get_prompt_config_by_id("answer_this")
    assert reactive is not None
    assert reactive.model == config.REACTIVE_MODEL
    assert reactive.max_tokens == config.REACTIVE_MAX_TOKENS

    post = get_prompt_config_by_id("meeting_summary")
    assert post is not None
    assert post.model == config.POST_MEETING_MODEL
    assert post.max_tokens == config.POST_MEETING_MAX_TOKENS


@pytest.mark.unit
def test_ask_prompt_config_resolvable_by_id():
    """The freeform Ask prompt is resolvable but is not a registry button."""
    cfg = get_prompt_config_by_id("ask")
    assert cfg is ASK_PROMPT_CONFIG
    assert cfg.max_tokens == config.ASK_MAX_TOKENS
    assert "{question}" in cfg.template
