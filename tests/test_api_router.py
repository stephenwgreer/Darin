"""Tests for the FastAPI API router (web/api_router.py).

Uses FastAPI TestClient with a mocked AppController + SSEEventBus.
All endpoints require ?token= via TokenAuthMiddleware.
"""

from __future__ import annotations

import pathlib
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from storage.app_config import AppConfigStore
from web.api_router import create_router
from web.sse_event_bus import SSEEventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TOKEN = "test-token-xyz"


def make_client(bus: SSEEventBus | None = None, controller=None, app_cfg_store=None) -> TestClient:
    """Build a TestClient with a minimal FastAPI app + the router under test."""
    if bus is None:
        bus = SSEEventBus()
    if controller is None:
        controller = _mock_controller()
    if app_cfg_store is None:
        tmp = pathlib.Path(tempfile.mkdtemp()) / "config.json"
        app_cfg_store = AppConfigStore(config_path=tmp)

    app = FastAPI()
    app.include_router(create_router(bus, controller, app_cfg_store))
    return TestClient(app, raise_server_exceptions=True)


def _mock_controller():
    ctrl = MagicMock()
    ctrl.meeting_state = "idle"
    ctrl.elapsed_seconds = 0
    ctrl.persona = "general"
    ctrl.get_meeting_transcript.return_value = "hello world"
    ctrl.get_saved_analyses.return_value = {}
    ctrl.start_meeting = AsyncMock()
    ctrl.stop_meeting = AsyncMock()
    ctrl.reset_to_idle = AsyncMock()
    ctrl.run_reactive_prompt = MagicMock(return_value=True)
    ctrl.dismiss_card = MagicMock(return_value=True)
    return ctrl


# ---------------------------------------------------------------------------
# /api/state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_state_idle() -> None:
    ctrl = _mock_controller()
    ctrl.meeting_state = "idle"
    ctrl.elapsed_seconds = 0
    client = make_client(controller=ctrl)

    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.json() == {"state": "idle", "elapsed": 0}


@pytest.mark.unit
def test_get_state_active() -> None:
    ctrl = _mock_controller()
    ctrl.meeting_state = "active"
    ctrl.elapsed_seconds = 127
    client = make_client(controller=ctrl)

    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.json() == {"state": "active", "elapsed": 127}


# ---------------------------------------------------------------------------
# /api/start_meeting, /api/stop_meeting, /api/reset
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_start_meeting_returns_ok() -> None:
    client = make_client()
    resp = client.post("/api/start_meeting")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.unit
def test_start_meeting_already_active_returns_409() -> None:
    from app_controller import MeetingAlreadyActiveError

    ctrl = _mock_controller()
    ctrl.start_meeting = AsyncMock(side_effect=MeetingAlreadyActiveError("already active"))
    client = make_client(controller=ctrl)
    resp = client.post("/api/start_meeting")
    assert resp.status_code == 409


@pytest.mark.unit
def test_start_meeting_capture_failure_returns_503() -> None:
    from app_controller import MeetingStartError

    ctrl = _mock_controller()
    ctrl.start_meeting = AsyncMock(side_effect=MeetingStartError("no devices"))
    client = make_client(controller=ctrl)
    resp = client.post("/api/start_meeting")
    assert resp.status_code == 503


@pytest.mark.unit
def test_stop_meeting_returns_ok() -> None:
    client = make_client()
    resp = client.post("/api/stop_meeting")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.unit
def test_reset_returns_ok() -> None:
    client = make_client()
    resp = client.post("/api/reset")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /api/run_prompt
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_prompt_unknown_id_returns_404() -> None:
    client = make_client()
    resp = client.post("/api/run_prompt", json={"prompt_id": "does_not_exist"})
    assert resp.status_code == 404


@pytest.mark.unit
def test_run_prompt_reactive_card_prompt_uses_reactive_lane() -> None:
    """Card prompts (the 5 reactive buttons) go through run_reactive_prompt."""
    ctrl = _mock_controller()
    ctrl.run_prompt = MagicMock()
    client = make_client(controller=ctrl)

    resp = client.post("/api/run_prompt", json={"prompt_id": "answer_this"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    ctrl.run_reactive_prompt.assert_called_once()
    assert ctrl.run_reactive_prompt.call_args.args[0].id == "answer_this"
    ctrl.run_prompt.assert_not_called()


@pytest.mark.unit
def test_run_prompt_same_button_in_flight_returns_409() -> None:
    """run_reactive_prompt returning False (same prompt in flight) → 409."""
    ctrl = _mock_controller()
    ctrl.run_reactive_prompt = MagicMock(return_value=False)
    client = make_client(controller=ctrl)

    resp = client.post("/api/run_prompt", json={"prompt_id": "fact_check"})
    assert resp.status_code == 409


@pytest.mark.unit
def test_run_prompt_long_form_prompt_uses_legacy_path() -> None:
    """Non-card prompts (post-meeting templates) go through controller.run_prompt."""
    ctrl = _mock_controller()
    ctrl.run_prompt = MagicMock()
    client = make_client(controller=ctrl)

    resp = client.post("/api/run_prompt", json={"prompt_id": "meeting_summary"})
    assert resp.status_code == 200
    ctrl.run_prompt.assert_called_once()
    ctrl.run_reactive_prompt.assert_not_called()


@pytest.mark.unit
def test_run_prompt_resolves_ask_config() -> None:
    """'ask' lives off-registry but resolves via get_prompt_config_by_id."""
    ctrl = _mock_controller()
    client = make_client(controller=ctrl)

    resp = client.post("/api/run_prompt", json={"prompt_id": "ask"})
    assert resp.status_code == 200
    ctrl.run_reactive_prompt.assert_called_once()


# ---------------------------------------------------------------------------
# /api/run_post_meeting_prompt
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_post_meeting_prompt_unknown_id_returns_404() -> None:
    client = make_client()
    resp = client.post("/api/run_post_meeting_prompt", json={"prompt_id": "no_such_prompt"})
    assert resp.status_code == 404


@pytest.mark.unit
def test_run_post_meeting_prompt_rejected_returns_409() -> None:
    """Long-form streaming is single-flight — a rejected run maps to 409."""
    ctrl = _mock_controller()
    ctrl.run_post_meeting_prompt = MagicMock(return_value=False)
    client = make_client(controller=ctrl)
    resp = client.post("/api/run_post_meeting_prompt", json={"prompt_id": "meeting_summary"})
    assert resp.status_code == 409


@pytest.mark.unit
def test_run_prompt_long_form_rejected_returns_409() -> None:
    ctrl = _mock_controller()
    ctrl.run_prompt = MagicMock(return_value=False)
    client = make_client(controller=ctrl)
    resp = client.post("/api/run_prompt", json={"prompt_id": "meeting_summary"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /api/ask
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ask_returns_ok_when_accepted() -> None:
    ctrl = _mock_controller()
    ctrl.ask_question = MagicMock(return_value=True)
    client = make_client(controller=ctrl)
    resp = client.post("/api/ask", json={"question": "What was decided?"})
    assert resp.status_code == 200
    ctrl.ask_question.assert_called_once()


@pytest.mark.unit
def test_ask_in_flight_returns_409() -> None:
    """A duplicate ask must NOT be reported as 200 ok — it maps to 409."""
    ctrl = _mock_controller()
    ctrl.ask_question = MagicMock(return_value=False)
    client = make_client(controller=ctrl)
    resp = client.post("/api/ask", json={"question": "What was decided?"})
    assert resp.status_code == 409


@pytest.mark.unit
def test_historical_ask_in_flight_returns_409() -> None:
    ctrl = _mock_controller()
    ctrl.ask_question = MagicMock(return_value=False)
    ctrl.meeting_store = MagicMock()
    ctrl.meeting_store.get_full_transcript.return_value = "some transcript"
    client = make_client(controller=ctrl)
    resp = client.post("/api/meetings/2026-07-09_141323/ask", json={"question": "hi?"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /api/transcribe_last_n
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_transcribe_last_n_calls_controller() -> None:
    ctrl = _mock_controller()
    ctrl.transcribe_last_n_seconds = MagicMock()
    client = make_client(controller=ctrl)

    resp = client.post("/api/transcribe_last_n", json={"seconds": 30})
    assert resp.status_code == 200
    ctrl.transcribe_last_n_seconds.assert_called_once_with(30)


# ---------------------------------------------------------------------------
# /api/transcript
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_transcript_returns_text() -> None:
    ctrl = _mock_controller()
    ctrl.get_meeting_transcript.return_value = "some transcript text"
    client = make_client(controller=ctrl)

    resp = client.get("/api/transcript")
    assert resp.status_code == 200
    assert resp.json()["transcript"] == "some transcript text"


# ---------------------------------------------------------------------------
# /api/saved_analyses
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_saved_analyses_empty() -> None:
    ctrl = _mock_controller()
    ctrl.get_saved_analyses.return_value = {}
    client = make_client(controller=ctrl)

    resp = client.get("/api/saved_analyses")
    assert resp.status_code == 200
    assert resp.json() == {"analyses": {}}


@pytest.mark.unit
def test_get_saved_analyses_with_data() -> None:
    ctrl = _mock_controller()
    ctrl.get_saved_analyses.return_value = {"prompt_a": "some text", "prompt_b": ""}
    client = make_client(controller=ctrl)

    resp = client.get("/api/saved_analyses")
    data = resp.json()["analyses"]
    assert data["prompt_a"] is True
    assert data["prompt_b"] is False


# ---------------------------------------------------------------------------
# /api/prompts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_prompts_returns_dict() -> None:
    client = make_client()
    resp = client.get("/api/prompts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ---------------------------------------------------------------------------
# /api/settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_settings_returns_default_path():
    client = make_client()
    resp = client.get(f"/api/settings?token={TOKEN}")
    assert resp.status_code == 200
    assert "storage_path" in resp.json()


@pytest.mark.unit
def test_post_settings_saves_and_rebinds_stores(tmp_path):
    """Changing storage_path persists AND rebinds MeetingStore + ContextPack live."""
    store = AppConfigStore(config_path=tmp_path / "config.json")
    ctrl = _mock_controller()
    new_path = str(tmp_path / "new_store")
    client = make_client(controller=ctrl, app_cfg_store=store)
    resp = client.post(f"/api/settings?token={TOKEN}", json={"storage_path": new_path})
    assert resp.status_code == 200
    assert store.load().storage_path == new_path
    # Live rebind — no restart needed
    from services.context_pack import ContextPack
    from storage.meeting_store import MeetingStore

    assert isinstance(ctrl.meeting_store, MeetingStore)
    assert isinstance(ctrl.context_pack, ContextPack)


@pytest.mark.unit
def test_post_settings_without_path_preserves_stored_path(tmp_path):
    """F4 regression: a save that omits storage_path (blank field) must persist
    the other settings and leave the stored path unchanged — not 400 or wipe it."""
    store = AppConfigStore(config_path=tmp_path / "config.json")
    cfg = store.load()
    cfg.storage_path = str(tmp_path / "keep_me")
    store.save(cfg)
    client = make_client(app_cfg_store=store)

    resp = client.post(
        f"/api/settings?token={TOKEN}",
        json={"background_style": "darin", "auto_hide_expired": True},
    )
    assert resp.status_code == 200
    saved = store.load()
    assert saved.storage_path == str(tmp_path / "keep_me")
    assert saved.background_style == "darin"
    assert saved.auto_hide_expired is True


@pytest.mark.unit
def test_post_settings_rejects_relative_path(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.post(f"/api/settings?token={TOKEN}", json={"storage_path": "relative/path"})
    assert resp.status_code == 400


@pytest.mark.unit
def test_post_settings_path_change_blocked_during_meeting(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    ctrl = _mock_controller()
    ctrl.meeting_state = "active"
    client = make_client(controller=ctrl, app_cfg_store=store)
    resp = client.post(
        f"/api/settings?token={TOKEN}", json={"storage_path": str(tmp_path / "elsewhere")}
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /api/models + custom endpoints (F2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_models_lists_anthropic_builtins():
    client = make_client()
    resp = client.get(f"/api/models?token={TOKEN}")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["models"]]
    assert "claude-sonnet-5" in ids
    assert "claude-haiku-4-5" in ids


@pytest.mark.unit
def test_get_models_includes_custom_endpoints(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.post(
        f"/api/settings?token={TOKEN}",
        json={
            "storage_path": str(tmp_path),
            "custom_endpoints": [
                {
                    "id": "groq",
                    "label": "Groq",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model_name": "llama-3.3-70b",
                    "api_key": "gsk_secret_key",
                }
            ],
        },
    )
    models = {m["id"]: m for m in client.get(f"/api/models?token={TOKEN}").json()["models"]}
    assert models["groq"]["provider"] == "openai_compat"
    assert models["groq"]["supports_web_search"] is False


@pytest.mark.unit
def test_custom_endpoint_api_key_masked_on_read(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.post(
        f"/api/settings?token={TOKEN}",
        json={
            "storage_path": str(tmp_path),
            "custom_endpoints": [
                {
                    "id": "groq",
                    "label": "Groq",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model_name": "m",
                    "api_key": "gsk_secret_key",
                }
            ],
        },
    )
    ep = client.get(f"/api/settings?token={TOKEN}").json()["custom_endpoints"][0]
    assert "gsk_secret_key" not in ep["api_key"]
    assert ep["api_key"].endswith("_key")  # last 4 chars only
    # Stored value is still the full key.
    assert store.load().custom_endpoints[0].api_key == "gsk_secret_key"


@pytest.mark.unit
def test_custom_endpoint_unchanged_sentinel_keeps_stored_key(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    body = {
        "storage_path": str(tmp_path),
        "custom_endpoints": [
            {
                "id": "groq",
                "label": "Groq",
                "base_url": "https://api.groq.com/openai/v1",
                "model_name": "m",
                "api_key": "gsk_original",
            }
        ],
    }
    client.post(f"/api/settings?token={TOKEN}", json=body)
    # Re-save with the sentinel + a new label.
    body["custom_endpoints"][0]["api_key"] = "__unchanged__"
    body["custom_endpoints"][0]["label"] = "Groq Renamed"
    client.post(f"/api/settings?token={TOKEN}", json=body)
    stored = store.load().custom_endpoints[0]
    assert stored.api_key == "gsk_original"
    assert stored.label == "Groq Renamed"


@pytest.mark.unit
def test_custom_endpoint_rejects_non_http_base_url(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.post(
        f"/api/settings?token={TOKEN}",
        json={
            "storage_path": str(tmp_path),
            "custom_endpoints": [
                {"id": "bad", "label": "B", "base_url": "ftp://x", "model_name": "m"}
            ],
        },
    )
    assert resp.status_code == 400


@pytest.mark.unit
def test_custom_endpoint_rejects_duplicate_ids(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    ep = {"id": "dup", "label": "D", "base_url": "https://x/v1", "model_name": "m"}
    resp = client.post(
        f"/api/settings?token={TOKEN}",
        json={"storage_path": str(tmp_path), "custom_endpoints": [ep, dict(ep)]},
    )
    assert resp.status_code == 400


@pytest.mark.unit
def test_settings_without_endpoints_preserves_existing(tmp_path):
    """A settings POST that omits custom_endpoints must not wipe them."""
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.post(
        f"/api/settings?token={TOKEN}",
        json={
            "storage_path": str(tmp_path),
            "custom_endpoints": [
                {"id": "groq", "label": "G", "base_url": "https://x/v1", "model_name": "m"}
            ],
        },
    )
    # Second POST omits custom_endpoints entirely.
    client.post(f"/api/settings?token={TOKEN}", json={"storage_path": str(tmp_path)})
    assert [e.id for e in store.load().custom_endpoints] == ["groq"]


@pytest.mark.unit
def test_settings_watcher_model_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.post(
        f"/api/settings?token={TOKEN}",
        json={"storage_path": str(tmp_path), "watcher_model": "groq"},
    )
    assert store.load().watcher_model == "groq"
    assert client.get(f"/api/settings?token={TOKEN}").json()["watcher_model"] == "groq"


@pytest.mark.unit
def test_settings_auto_hide_expired_round_trip(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    # Default is exposed as False.
    assert client.get(f"/api/settings?token={TOKEN}").json()["auto_hide_expired"] is False
    client.post(
        f"/api/settings?token={TOKEN}",
        json={"storage_path": str(tmp_path), "auto_hide_expired": True},
    )
    assert store.load().auto_hide_expired is True
    assert client.get(f"/api/settings?token={TOKEN}").json()["auto_hide_expired"] is True


# ---------------------------------------------------------------------------
# /api/meetings
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_meetings_returns_list():
    ctrl = _mock_controller()
    ctrl.meeting_store = MagicMock()
    ctrl.meeting_store.list_meetings.return_value = []
    client = make_client(controller=ctrl)
    resp = client.get(f"/api/meetings?token={TOKEN}")
    assert resp.status_code == 200
    assert resp.json()["meetings"] == []


@pytest.mark.unit
def test_get_meeting_transcript_not_found():
    ctrl = _mock_controller()
    ctrl.meeting_store = MagicMock()
    ctrl.meeting_store.get_meeting.return_value = None
    client = make_client(controller=ctrl)
    resp = client.get(f"/api/meetings/nonexistent/transcript?token={TOKEN}")
    assert resp.status_code == 404


@pytest.mark.unit
def test_get_meeting_cards_returns_persisted_cards():
    ctrl = _mock_controller()
    ctrl.meeting_store = MagicMock()
    ctrl.meeting_store.get_cards.return_value = [
        {"id": "card_1", "headline": "First", "cues": ["ask pricing"], "ts": "2026-07-09T00:00:00"}
    ]
    client = make_client(controller=ctrl)
    resp = client.get(f"/api/meetings/2026-07-09_141323/cards?token={TOKEN}")
    assert resp.status_code == 200
    cards = resp.json()["cards"]
    assert len(cards) == 1
    assert cards[0]["headline"] == "First"
    ctrl.meeting_store.get_cards.assert_called_once_with("2026-07-09_141323")


@pytest.mark.unit
def test_get_meeting_cards_rejects_bad_id():
    ctrl = _mock_controller()
    ctrl.meeting_store = MagicMock()
    client = make_client(controller=ctrl)
    resp = client.get(f"/api/meetings/..%2Fescape/cards?token={TOKEN}")
    assert resp.status_code in (400, 404)
    ctrl.meeting_store.get_cards.assert_not_called()


@pytest.mark.unit
def test_get_meeting_cards_no_store():
    ctrl = _mock_controller()
    ctrl.meeting_store = None
    client = make_client(controller=ctrl)
    resp = client.get(f"/api/meetings/2026-07-09_141323/cards?token={TOKEN}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/custom_prompts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_custom_prompts_returns_list(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.get(f"/api/custom_prompts?token={TOKEN}")
    assert resp.status_code == 200
    assert "prompts" in resp.json()


@pytest.mark.unit
def test_create_custom_prompt(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.post(
        f"/api/custom_prompts?token={TOKEN}",
        json={
            "button_text": "My Prompt",
            "output_title": "My Output",
            "template": "Analyze: {transcript}",
        },
    )
    assert resp.status_code == 200
    assert "id" in resp.json()
    assert len(store.load().custom_prompts) == 1


@pytest.mark.unit
def test_delete_custom_prompt(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    r = client.post(
        f"/api/custom_prompts?token={TOKEN}",
        json={"button_text": "Del Me", "output_title": "Out", "template": "t"},
    )
    pid = r.json()["id"]
    resp = client.delete(f"/api/custom_prompts/{pid}?token={TOKEN}")
    assert resp.status_code == 200
    assert len(store.load().custom_prompts) == 0


@pytest.mark.unit
def test_create_custom_prompt_round_trips_model_and_web_search(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.post(
        f"/api/custom_prompts?token={TOKEN}",
        json={
            "button_text": "Deep",
            "output_title": "Out",
            "template": "t",
            "model": "claude-sonnet-5",
            "web_search": True,
        },
    )
    assert resp.status_code == 200
    saved = store.load().custom_prompts[0]
    assert saved.model == "claude-sonnet-5"
    assert saved.web_search is True


@pytest.mark.unit
def test_update_custom_prompt_model_and_web_search(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    pid = client.post(
        f"/api/custom_prompts?token={TOKEN}",
        json={"button_text": "Mine", "output_title": "Out", "template": "t"},
    ).json()["id"]
    resp = client.put(
        f"/api/custom_prompts/{pid}?token={TOKEN}",
        json={"model": "claude-haiku-4-5", "web_search": True},
    )
    assert resp.status_code == 200
    saved = store.load().custom_prompts[0]
    assert saved.model == "claude-haiku-4-5"
    assert saved.web_search is True


@pytest.mark.unit
def test_update_builtin_prompt_writes_model_and_web_search_override(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.put(
        f"/api/custom_prompts/fact_check?token={TOKEN}",
        json={"model": "claude-haiku-4-5", "web_search": True},
    )
    assert resp.status_code == 200
    overrides = store.load().prompt_overrides["fact_check"]
    assert overrides["model"] == "claude-haiku-4-5"
    assert overrides["web_search"] is True


@pytest.mark.unit
def test_get_custom_prompts_includes_model_and_web_search(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.post(
        f"/api/custom_prompts?token={TOKEN}",
        json={
            "button_text": "Mine",
            "output_title": "Out",
            "template": "t",
            "model": "claude-sonnet-5",
            "web_search": True,
        },
    )
    prompts = client.get(f"/api/custom_prompts?token={TOKEN}").json()["prompts"]
    mine = next(p for p in prompts if p["button_text"] == "Mine")
    assert mine["model"] == "claude-sonnet-5"
    assert mine["web_search"] is True
    # Built-ins expose their model too so the editor dropdown can preselect it.
    fact = next(p for p in prompts if p["id"] == "fact_check")
    assert fact["model"] == "claude-sonnet-5"
    assert fact["web_search"] is False


@pytest.mark.unit
def test_post_settings_refreshes_model_registry(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    ctrl = _mock_controller()
    client = make_client(controller=ctrl, app_cfg_store=store)
    resp = client.post(
        f"/api/settings?token={TOKEN}",
        json={
            "storage_path": str(tmp_path / "meetings"),
            "custom_endpoints": [
                {
                    "id": "groq",
                    "label": "Groq",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model_name": "llama-3.3-70b",
                    "api_key": "sk-live-1234",
                }
            ],
        },
    )
    assert resp.status_code == 200
    # The router rebound a fresh registry onto the controller's api client that
    # can resolve the newly-saved custom endpoint.
    registry = ctrl.api_client.model_registry
    spec = registry.resolve("groq")
    assert spec is not None
    assert spec.provider == "openai_compat"


@pytest.mark.unit
def test_get_prompts_excludes_deleted_builtin(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.delete(f"/api/custom_prompts/fact_check?token={TOKEN}")
    resp = client.get(f"/api/prompts?token={TOKEN}")
    all_ids = [p["id"] for bucket in resp.json().values() for p in bucket]
    assert "fact_check" not in all_ids


# ---------------------------------------------------------------------------
# /api/prompts — new registry grouping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_prompts_grouped_by_bucket(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.get(f"/api/prompts?token={TOKEN}")
    data = resp.json()
    assert set(data.keys()) == {"reactive", "post_meeting", "custom"}
    reactive_ids = [p["id"] for p in data["reactive"]]
    assert reactive_ids == [
        "answer_this",
        "fact_check",
        "reframe",
        "where_are_we",
        "next_step",
        "ask_this",
        "deep_dive",
    ]
    post_ids = [p["id"] for p in data["post_meeting"]]
    assert post_ids == ["meeting_summary", "action_items", "key_decisions"]
    assert data["custom"] == []


@pytest.mark.unit
def test_get_prompts_custom_prompts_in_custom_group(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.post(
        f"/api/custom_prompts?token={TOKEN}",
        json={"button_text": "Mine", "output_title": "Out", "template": "do it"},
    )
    resp = client.get(f"/api/prompts?token={TOKEN}")
    custom = resp.json()["custom"]
    assert len(custom) == 1
    assert custom[0]["button_text"] == "Mine"
    assert custom[0]["template_type"] == "card"


# ---------------------------------------------------------------------------
# /api/context — context pack GET/PUT
# ---------------------------------------------------------------------------


def _client_with_context_pack(tmp_path):
    from services.context_pack import ContextPack

    ctrl = _mock_controller()
    ctrl.context_pack = ContextPack(tmp_path)
    store = AppConfigStore(config_path=tmp_path / "config.json")
    return make_client(controller=ctrl, app_cfg_store=store), ctrl


@pytest.mark.unit
def test_get_context_returns_three_docs(tmp_path):
    client, _ = _client_with_context_pack(tmp_path)
    resp = client.get(f"/api/context?token={TOKEN}")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"profile", "products", "known_issues"}


@pytest.mark.unit
def test_put_context_round_trip(tmp_path):
    client, _ = _client_with_context_pack(tmp_path)
    resp = client.put(
        f"/api/context?token={TOKEN}",
        json={"profile": "# Me\nI sell things.", "products": "# Products\nWidget v2"},
    )
    assert resp.status_code == 200
    data = client.get(f"/api/context?token={TOKEN}").json()
    assert data["profile"] == "# Me\nI sell things."
    assert data["products"] == "# Products\nWidget v2"
    assert data["known_issues"] == ""  # untouched field stays empty


@pytest.mark.unit
def test_put_context_partial_update_preserves_other_docs(tmp_path):
    client, _ = _client_with_context_pack(tmp_path)
    client.put(f"/api/context?token={TOKEN}", json={"profile": "original profile"})
    client.put(f"/api/context?token={TOKEN}", json={"known_issues": "flaky sync"})
    data = client.get(f"/api/context?token={TOKEN}").json()
    assert data["profile"] == "original profile"
    assert data["known_issues"] == "flaky sync"


@pytest.mark.unit
def test_context_unavailable_returns_503(tmp_path):
    ctrl = _mock_controller()
    ctrl.context_pack = None
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(controller=ctrl, app_cfg_store=store)
    assert client.get(f"/api/context?token={TOKEN}").status_code == 503
    assert client.put(f"/api/context?token={TOKEN}", json={"profile": "x"}).status_code == 503


# ---------------------------------------------------------------------------
# /api/persona
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_persona_returns_controller_persona():
    ctrl = _mock_controller()
    ctrl.persona = "sales"
    client = make_client(controller=ctrl)
    resp = client.get(f"/api/persona?token={TOKEN}")
    assert resp.status_code == 200
    assert resp.json() == {"persona": "sales"}


@pytest.mark.unit
def test_post_persona_sets_controller_and_persists(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    ctrl = _mock_controller()
    client = make_client(controller=ctrl, app_cfg_store=store)
    resp = client.post(f"/api/persona?token={TOKEN}", json={"persona": "technical"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "persona": "technical"}
    assert ctrl.persona == "technical"
    assert store.load().persona == "technical"


@pytest.mark.unit
def test_post_persona_rejects_invalid_value(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    ctrl = _mock_controller()
    client = make_client(controller=ctrl, app_cfg_store=store)
    resp = client.post(f"/api/persona?token={TOKEN}", json={"persona": "pirate"})
    assert resp.status_code == 400
    assert ctrl.persona == "general"  # unchanged


# ---------------------------------------------------------------------------
# /api/cards/{card_id}/dismiss
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dismiss_card_ok():
    ctrl = _mock_controller()
    client = make_client(controller=ctrl)
    resp = client.post(f"/api/cards/card_ab12cd34ef56/dismiss?token={TOKEN}")
    assert resp.status_code == 200
    ctrl.dismiss_card.assert_called_once_with("card_ab12cd34ef56")


@pytest.mark.unit
def test_dismiss_card_unknown_returns_404():
    ctrl = _mock_controller()
    ctrl.dismiss_card = MagicMock(return_value=False)
    client = make_client(controller=ctrl)
    resp = client.post(f"/api/cards/card_000000000000/dismiss?token={TOKEN}")
    assert resp.status_code == 404


@pytest.mark.unit
def test_dismiss_card_invalid_id_rejected_before_controller():
    ctrl = _mock_controller()
    client = make_client(controller=ctrl)
    resp = client.post(f"/api/cards/bad.id/dismiss?token={TOKEN}")
    assert resp.status_code == 400
    ctrl.dismiss_card.assert_not_called()


# ---------------------------------------------------------------------------
# Path-parameter validation (traversal rejection)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_id",
    [
        "a.b",  # dots are the traversal building block — rejected outright
        "has%20space",  # decodes to "has space"
        "semi;colon",
        "-leading-dash",  # must start alphanumeric
    ],
)
def test_meeting_id_validation_rejects_unsafe_ids(bad_id: str) -> None:
    ctrl = _mock_controller()
    ctrl.meeting_store = MagicMock()
    client = make_client(controller=ctrl)

    resp = client.get(f"/api/meetings/{bad_id}/transcript?token={TOKEN}")
    assert resp.status_code == 400
    ctrl.meeting_store.get_meeting.assert_not_called()

    resp = client.post(f"/api/meetings/{bad_id}/ask?token={TOKEN}", json={"question": "hi?"})
    assert resp.status_code == 400


@pytest.mark.unit
def test_meeting_id_validation_accepts_store_format() -> None:
    ctrl = _mock_controller()
    ctrl.meeting_store = MagicMock()
    ctrl.meeting_store.get_meeting.return_value = None
    client = make_client(controller=ctrl)
    # Valid strftime-shaped id passes validation (then 404s on the mock store)
    resp = client.get(f"/api/meetings/2026-07-09_141323/transcript?token={TOKEN}")
    assert resp.status_code == 404
    ctrl.meeting_store.get_meeting.assert_called_once_with("2026-07-09_141323")
