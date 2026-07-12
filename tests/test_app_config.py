# tests/test_app_config.py
import pytest

from storage.app_config import (
    AppConfig,
    AppConfigStore,
    CustomEndpointConfig,
    CustomPromptConfig,
)


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


@pytest.mark.unit
def test_corrupt_config_backed_up_to_bak_before_fresh_start(tmp_path):
    """Wave 4 hardening: a corrupt config must be preserved, not silently lost."""
    p = tmp_path / "config.json"
    p.write_text("{ definitely not json")
    store = AppConfigStore(config_path=p)
    cfg = store.load()
    assert isinstance(cfg, AppConfig)
    bak = tmp_path / "config.json.bak"
    assert bak.exists()
    assert bak.read_text() == "{ definitely not json"
    # Original moved aside so the next save() writes a fresh file.
    assert not p.exists()


@pytest.mark.unit
def test_non_object_config_root_treated_as_corrupt(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('["valid json", "wrong shape"]')
    store = AppConfigStore(config_path=p)
    cfg = store.load()
    assert isinstance(cfg, AppConfig)
    assert (tmp_path / "config.json.bak").exists()


@pytest.mark.unit
def test_unknown_fields_in_custom_prompt_do_not_destroy_config(tmp_path):
    """A custom prompt with extra fields loads (extras dropped), rest intact."""
    import json

    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "storage_path": "/my/path",
                "custom_prompts": [
                    {
                        "id": "cp_ok",
                        "button_text": "OK",
                        "output_title": "Out",
                        "template": "T",
                        "future_field": "from a newer version",
                    }
                ],
                "deleted_prompt_ids": ["deal_risk"],
            }
        )
    )
    store = AppConfigStore(config_path=p)
    cfg = store.load()
    assert cfg.storage_path == "/my/path"
    assert cfg.deleted_prompt_ids == ["deal_risk"]
    assert len(cfg.custom_prompts) == 1
    assert cfg.custom_prompts[0].id == "cp_ok"
    # Not treated as corrupt — no backup created.
    assert not (tmp_path / "config.json.bak").exists()


@pytest.mark.unit
def test_malformed_custom_prompt_skipped_but_others_kept(tmp_path):
    import json

    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "custom_prompts": [
                    {"id": "cp_broken"},  # missing required fields
                    "not even a dict",
                    {
                        "id": "cp_good",
                        "button_text": "Good",
                        "output_title": "Out",
                        "template": "T",
                    },
                ],
            }
        )
    )
    store = AppConfigStore(config_path=p)
    cfg = store.load()
    assert [cp.id for cp in cfg.custom_prompts] == ["cp_good"]


@pytest.mark.unit
def test_custom_prompts_not_a_list_ignored(tmp_path):
    import json

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"custom_prompts": {"oops": "a dict"}, "persona": "sales"}))
    store = AppConfigStore(config_path=p)
    cfg = store.load()
    assert cfg.custom_prompts == []
    assert cfg.persona == "sales"


@pytest.mark.unit
def test_custom_endpoints_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    cfg.custom_endpoints.append(
        CustomEndpointConfig(
            id="groq",
            label="Groq",
            base_url="https://api.groq.com/openai/v1",
            model_name="llama-3.3-70b",
            api_key="gsk_secret",
        )
    )
    store.save(cfg)
    reloaded = store.load()
    assert len(reloaded.custom_endpoints) == 1
    ep = reloaded.custom_endpoints[0]
    assert ep.id == "groq"
    assert ep.api_key == "gsk_secret"


@pytest.mark.unit
def test_watcher_model_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    assert cfg.watcher_model is None
    cfg.watcher_model = "groq"
    store.save(cfg)
    assert store.load().watcher_model == "groq"


@pytest.mark.unit
def test_auto_hide_expired_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    assert cfg.auto_hide_expired is False  # F4 retention default: keep cards
    cfg.auto_hide_expired = True
    store.save(cfg)
    assert store.load().auto_hide_expired is True


@pytest.mark.unit
def test_custom_prompt_model_and_web_search_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    cfg.custom_prompts.append(
        CustomPromptConfig(
            id="cp_x",
            button_text="X",
            output_title="X Out",
            template="t",
            model="groq",
            web_search=True,
        )
    )
    store.save(cfg)
    reloaded = store.load().custom_prompts[0]
    assert reloaded.model == "groq"
    assert reloaded.web_search is True


@pytest.mark.unit
def test_malformed_custom_endpoint_skipped(tmp_path):
    import json

    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "custom_endpoints": [
                    {"id": "broken"},  # missing required fields
                    "not a dict",
                    {
                        "id": "ok",
                        "label": "OK",
                        "base_url": "https://x/v1",
                        "model_name": "m",
                    },
                ]
            }
        )
    )
    store = AppConfigStore(config_path=p)
    cfg = store.load()
    assert [e.id for e in cfg.custom_endpoints] == ["ok"]
    assert cfg.custom_endpoints[0].api_key == ""
