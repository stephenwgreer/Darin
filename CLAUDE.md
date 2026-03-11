# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Darin Audio Assistant — a real-time meeting transcription and AI analysis tool. It records audio continuously, streams transcriptions via Deepgram, and sends transcripts to Claude for analysis via a NiceGUI web interface.

## Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run python main_nicegui.py

# Run all tests
pytest

# Run a specific test file or function
pytest tests/test_api_client.py
pytest tests/test_api_client.py::test_anthropic_client_reuse

# Run only unit or integration tests
pytest -m unit
pytest -m integration

# Lint and format
ruff check . --fix
ruff format .

# Type check
mypy .
```

**WSL agents**: Set `UV_PROJECT_ENVIRONMENT=.venv-linux` before `uv sync`.

## Environment Variables

Required in `.env`:
- `ANTHROPIC_API_KEY` — Claude API key
- `DEEPGRAM_API_KEY` — Deepgram API key
- `TEST_AUDIO_WAV` (optional) — Path to WAV file; bypasses live transcription for testing

## Architecture

The app is organized into five distinct layers:

### 1. Frontend — `ui/`
NiceGUI web components. `ui/pages/meeting_page.py` is the main page that wires all components together. UI is decoupled from business logic via callbacks — it provides callbacks to AppController and is responsible for marshalling background thread updates to the main thread.

### 2. Controller — `app_controller.py`
Framework-agnostic orchestration. Owns the meeting state machine (`idle → active → post_meeting`), recording lifecycle, transcription dispatch, and prompt execution. Has no UI imports — communicates with UI via callbacks registered at init.

### 3. Audio — `audio/recorder.py`
`ContinuousRecorder` maintains a rolling circular buffer (deque, 3–5 minutes). A background thread continuously records; captured audio chunks are fan-out dispatched to registered consumers. Thread-safe with locks.

### 4. API — `api/`
- `client.py` — `ApiClient`: lazy-loaded Anthropic client, streaming, exponential backoff retry
- `deepgram_streaming.py` — `DeepgramStreamingClient`: persistent WebSocket, asyncio event loop in daemon thread, real-time interim/final transcripts
- `anthropic_utils.py` / `deepgram_utils.py` — helpers and sync wrappers

### 5. Storage — `storage/`
`MeetingStore` uses SQLite (WAL mode) with thread-safe locking. Data models: `MeetingRecord`, `TranscriptSegment`, `MeetingAnalysis` (dataclasses in `storage/models.py`).

## Key Conventions

- **Callbacks for all cross-layer communication** — AppController takes callbacks at init; never imports UI code
- **All configuration via `config.py`** — loads from `.env`; validated at startup
- **Prompt templates** live in `prompts/templates.py` and `prompts/logic_templates.py`; registered via `prompts/registry.py`
- **Test markers**: `@pytest.mark.unit` / `@pytest.mark.integration`; 80% coverage minimum enforced
- **`tests/conftest.py`** stubs soundcard for CI/headless environments
- **Line length**: 100 characters (ruff); **Target**: Python 3.11

## Security (DAR2-34)

The app applies five localhost-only controls at startup:
1. Host restricted to `127.0.0.1`
2. Random ephemeral port (`port=0`)
3. Secret token middleware (validates `?token=` on all routes) — `middleware/token_auth.py`
4. FastAPI docs/OpenAPI endpoints disabled
5. Content-Security-Policy headers — `middleware/csp.py`

These controls are in `main_nicegui.py` and `security.py`. Do not weaken them.
