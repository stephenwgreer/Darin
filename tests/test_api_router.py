"""Tests for the FastAPI API router (web/api_router.py).

Uses FastAPI TestClient with a mocked AppController + SSEEventBus.
All endpoints require ?token= via TokenAuthMiddleware.
"""

from __future__ import annotations

import pathlib
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

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
    ctrl.get_meeting_transcript.return_value = "hello world"
    ctrl.get_saved_analyses.return_value = {}
    ctrl.start_meeting = AsyncMock()
    ctrl.stop_meeting = AsyncMock()
    ctrl.reset_to_idle = AsyncMock()
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
def test_run_prompt_valid_id_calls_controller() -> None:
    from prompts.registry import PROMPT_REGISTRY

    if not PROMPT_REGISTRY:
        pytest.skip("No prompts registered")

    cfg = PROMPT_REGISTRY[0]
    ctrl = _mock_controller()
    ctrl.run_prompt = MagicMock()
    client = make_client(controller=ctrl)

    resp = client.post("/api/run_prompt", json={"prompt_id": cfg.id})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    ctrl.run_prompt.assert_called_once()


# ---------------------------------------------------------------------------
# /api/run_post_meeting_prompt
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_post_meeting_prompt_unknown_id_returns_404() -> None:
    client = make_client()
    resp = client.post("/api/run_post_meeting_prompt", json={"prompt_id": "no_such_prompt"})
    assert resp.status_code == 404


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
def test_post_settings_saves_and_returns_updated(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    resp = client.post(f"/api/settings?token={TOKEN}", json={"storage_path": "/new/path"})
    assert resp.status_code == 200
    assert store.load().storage_path == "/new/path"


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
        json={"button_text": "My Prompt", "output_title": "My Output", "template": "Analyze: {transcript}"},
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
def test_get_prompts_excludes_deleted_builtin(tmp_path):
    store = AppConfigStore(config_path=tmp_path / "config.json")
    client = make_client(app_cfg_store=store)
    client.delete(f"/api/custom_prompts/deal_risk?token={TOKEN}")
    resp = client.get(f"/api/prompts?token={TOKEN}")
    all_ids = [p["id"] for bucket in resp.json().values() for p in bucket]
    assert "deal_risk" not in all_ids
