# tests/test_app_config.py
import pytest

from storage.app_config import AppConfig, AppConfigStore, CustomPromptConfig


@pytest.mark.unit
def test_default_config_uses_default_storage_path(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    assert "darin-audio-assistant" in cfg.storage_path


@pytest.mark.unit
def test_save_and_reload_storage_path(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    cfg.storage_path = "/custom/path"
    store.save(cfg)
    reloaded = store.load()
    assert reloaded.storage_path == "/custom/path"


@pytest.mark.unit
def test_save_and_reload_custom_prompt(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    cfg.custom_prompts.append(
        CustomPromptConfig(
            id="cp_test", button_text="Test", output_title="Test Out", template="Hello {transcript}"
        )
    )
    store.save(cfg)
    reloaded = store.load()
    assert len(reloaded.custom_prompts) == 1
    assert reloaded.custom_prompts[0].id == "cp_test"


@pytest.mark.unit
def test_deleted_prompt_ids_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    cfg.deleted_prompt_ids.append("deal_risk")
    store.save(cfg)
    reloaded = store.load()
    assert "deal_risk" in reloaded.deleted_prompt_ids


@pytest.mark.unit
def test_prompt_overrides_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    cfg.prompt_overrides["sentiment_analysis"] = {"button_text": "My Sentiment"}
    store.save(cfg)
    reloaded = store.load()
    assert reloaded.prompt_overrides["sentiment_analysis"]["button_text"] == "My Sentiment"


@pytest.mark.unit
def test_missing_config_file_returns_defaults(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "nonexistent.json")
    cfg = store.load()
    assert isinstance(cfg, AppConfig)
    assert cfg.custom_prompts == []
    assert cfg.deleted_prompt_ids == []


@pytest.mark.unit
def test_corrupt_config_file_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("not-json")
    store = AppConfigStore(config_path=p)
    cfg = store.load()
    assert isinstance(cfg, AppConfig)
