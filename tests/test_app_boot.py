"""Boot-time regression tests for the session-scoped capture rule (Wave 4).

Product rule (owner requirement): capture is SESSION-SCOPED. Nothing may
record at app boot — recording starts only with POST /start_meeting and
stops fully when the session ends. These tests guard the invariant that
``create_app()`` never touches audio devices or starts the recorder.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import web.app as web_app
from storage.app_config import AppConfigStore


@pytest.fixture
def hermetic_config_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point create_app's AppConfigStore at tmp_path so no user files are touched."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"storage_path": str(tmp_path / "meetings")}),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_app, "AppConfigStore", lambda: AppConfigStore(config_path=config_path))
    return config_path


def test_create_app_does_not_start_recording(hermetic_config_store) -> None:
    """create_app() must never start capture — recording is session-scoped."""
    app = web_app.create_app("test-token-boot")
    controller = app.state.controller
    assert controller.recorder.is_recording is False
    assert controller.is_streaming is False
    assert controller.meeting_state == "idle"


def test_create_app_source_has_no_boot_recording_call() -> None:
    """Belt-and-braces: no start_recording call may exist in web/app.py."""
    source = Path(web_app.__file__).read_text(encoding="utf-8")
    assert "start_recording" not in source


def test_create_app_requires_no_audio_devices(hermetic_config_store) -> None:
    """Boot must succeed in an environment with zero audio hardware (CI/WSL)."""
    app = web_app.create_app("test-token-boot")
    # The recorder object exists but has resolved no devices yet — device
    # resolution is deferred to start_recording() (fresh per session).
    controller = app.state.controller
    assert not controller.recorder.is_recording
