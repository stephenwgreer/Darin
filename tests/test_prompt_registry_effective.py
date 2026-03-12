# tests/test_prompt_registry_effective.py
import pytest

from prompts.registry import get_effective_registry
from storage.app_config import AppConfig, CustomPromptConfig


@pytest.mark.unit
def test_effective_registry_returns_all_builtins_by_default():
    cfg = AppConfig()
    registry = get_effective_registry(cfg)
    ids = [p.id for p in registry]
    assert "sentiment_analysis" in ids
    assert "deal_risk" in ids


@pytest.mark.unit
def test_effective_registry_excludes_deleted_ids():
    cfg = AppConfig(deleted_prompt_ids=["deal_risk"])
    registry = get_effective_registry(cfg)
    ids = [p.id for p in registry]
    assert "deal_risk" not in ids
    assert "sentiment_analysis" in ids


@pytest.mark.unit
def test_effective_registry_applies_overrides():
    cfg = AppConfig(prompt_overrides={"sentiment_analysis": {"button_text": "My Sentiment"}})
    registry = get_effective_registry(cfg)
    p = next(p for p in registry if p.id == "sentiment_analysis")
    assert p.button_text == "My Sentiment"


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
def test_get_effective_prompt_by_id_finds_custom(tmp_path):
    cfg = AppConfig(
        custom_prompts=[
            CustomPromptConfig(id="cp_bar", button_text="Bar", output_title="Bar Out", template="tmpl")
        ]
    )
    registry = get_effective_registry(cfg)
    p = next((p for p in registry if p.id == "cp_bar"), None)
    assert p is not None
    assert p.template == "tmpl"
