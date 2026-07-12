# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Darin Audio Assistant — a real-time meeting copilot. During a session it captures both sides of a call (your mic + speaker loopback), streams transcription via Deepgram, and surfaces glanceable "cards" from Claude — proactively (a watcher ticks on utterance ends) and reactively (5 action buttons + a freeform Ask box). Localhost FastAPI/uvicorn server with a vanilla-JS browser SPA over SSE.

## Commands

```bash
# Install dependencies
uv sync

# Run the application (opens browser with one-time auth token)
uv run python main.py

# Run all tests (coverage gate: 80%)
uv run pytest

# Iterate without the coverage gate
uv run pytest -q --no-cov

# Run a specific test file or function
uv run pytest tests/test_api_client.py
uv run pytest tests/test_api_client.py::test_anthropic_client_reuse

# Run only unit or integration tests
uv run pytest -m unit
uv run pytest -m integration

# Lint and format
uv run ruff check . --fix
uv run ruff format .

# Type check (advisory — large pre-existing strict-mode backlog; not a CI gate)
uv run mypy .
```

**WSL agents**: Set `UV_PROJECT_ENVIRONMENT=.venv-linux` before `uv sync`. There is no audio hardware in WSL/CI — `tests/conftest.py` stubs `soundcard`, and all tests must mock devices/websockets.

## Environment Variables

Required in `.env`:
- `ANTHROPIC_API_KEY` — Claude API key
- `DEEPGRAM_API_KEY` — Deepgram API key
- `TEST_AUDIO_WAV` (optional) — Path to WAV file; bypasses live transcription for testing

## Current Architecture (2026-07 rewrite)

**Session-scoped capture (product rule):** nothing records at app boot. `web/app.py create_app()` never starts the recorder; capture starts with `POST /start_meeting` and fully stops when the session ends. The rolling buffer only exists within a session. Regression-guarded in `tests/test_app_boot.py`.

```
CAPTURE   audio/recorder.py — ContinuousRecorder: TWO WASAPI sources resolved
          fresh at every start_recording(): default mic = ME (col 0), speaker
          loopback = THEM (col 1). int16, 16 kHz, 100 ms chunks, shape (1600, 2).
          Missing source → zero-filled column + .sources_active flag, never a crash.
          48 kHz devices decimated 3:1 via numpy FIR (no scipy). Rolling 5-min
          deque; save_buffer()/get_last_n_seconds() return MONO int16 (no file writes).
STT       api/deepgram_streaming.py — Deepgram SDK v4, nova-3, 2-channel
          multichannel (ME/THEM attribution), interim_results, endpointing=300,
          utterance_end_ms=1000, keyterms. Transcript lines are "ME: ..."/"THEM: ...".
          Batch path: api/deepgram_utils.py (in-memory WAV, raises on failure).
LLM       api/client.py — cache-first request shape: [cached system = instructions
          + context pack] → [append-only transcript blocks, cache breakpoint on
          last] → [uncached per-request instruction]. Cards come from FORCED TOOL
          USE ("emit_cards" tool, schema in services/cards.py). No temperature.
          Usage/cost telemetry per call and per meeting.
MODELS    config.py tiers — WATCHER_MODEL=claude-haiku-4-5 (watcher, titles,
          rolling summary, map-reduce), REACTIVE_MODEL=claude-sonnet-5 (buttons/
          Ask, thinking disabled), POST_MEETING_MODEL=claude-sonnet-5 (long-form).
          Watcher lane: max_retries=0, timeout=8 s.
LANES     app_controller.py — per-lane concurrency (no global lock):
          • PROACTIVE: services/watcher.py — Haiku tick on utterance-end events;
            code-enforced rules (≥12 s between ticks AND ≥30 new words, 1 card/15 s,
            60 s per-type cooldown, 5-min topic dedupe, dismissed topics suppressed).
            Returns {} or ONE card. Runs in its own thread, session-scoped.
          • REACTIVE: one in-flight per prompt_id (same button rejected; different
            buttons concurrent). Context = rolling summary + last ~3 min verbatim.
          • BACKGROUND: unrestricted — titles, rolling summary (services/
            rolling_summary.py, ~every 5 min), post-meeting map-reduce (parallel).
CARDS     services/cards.py — single card schema for both lanes: {id, lane, type,
          trigger, headline ≤60, bullets ≤3×140, say_this, confidence, urgency,
          source, expires_in_s, topic_key}. Proactive cards expire; reactive pinned.
CONTEXT   services/context_pack.py — profile.md / products.md / known_issues.md
          under AppConfig.storage_path/context/, loaded into the cached system
          block (~20k-token cap). Editable via Settings → PUT /api/context.
PROMPTS   prompts/registry.py — 5 reactive card prompts (answer_this, fact_check,
          reframe, where_are_we, next_step) + off-registry "ask" + 3 post-meeting
          long-form (meeting_summary, action_items, key_decisions) + title/watcher/
          rolling-summary prompts. Persona toggle (general|sales|technical) —
          sales_signal watcher trigger only arms for persona=sales. Custom user
          prompts run reactive-style.
WEB       web/sse_event_bus.py — multi-client fan-out (per-client asyncio.Queue,
          thread-safe publish via call_soon_threadsafe, 15 s keepalive, no polling).
          web/api_router.py — all blocking work via asyncio.to_thread; strict id
          regex on path params. web/static/ — card feed UI, live ME/THEM transcript
          strip, 5-button action bar, persona toggle, Context Pack editor;
          rAF-batched SSE rendering; boot.js keeps CSP script-src 'self' (no inline).
STORAGE   storage/meeting_store.py — flat files per meeting (meta.txt,
          transcript.txt, segments.tsv, analyses/); newline-sanitized segments;
          corrupt meeting dirs are skipped, never fatal. storage/app_config.py —
          ~/.darin-audio-assistant/config.json; corrupt config is backed up to
          config.json.bak (loud log) before starting fresh.
```

## Key Conventions

- **Callbacks for all cross-layer communication** — `AppController` is framework-agnostic (no web imports); UI communication via callbacks → SSE
- **All configuration via `config.py`** — loads from `.env`; validated at startup
- **loguru logging with keyword fields** (`logger.info("msg", key=value)`), type hints, DAR ticket references in docstrings
- **Test markers**: `@pytest.mark.unit` / `@pytest.mark.integration`; 80% coverage gate enforced (use `--no-cov` while iterating)
- **Never require real audio devices or live APIs in tests** — mock soundcard/websockets/Anthropic
- **Line length**: 100 characters (ruff); **Target**: Python 3.11+

## Security (DAR2-34)

The app applies five localhost-only controls at startup:
1. Host restricted to `127.0.0.1` (`main.py`)
2. Random ephemeral port (`port=0`) (`main.py`)
3. Secret token middleware (validates `?token=` on all routes) — `middleware/token_auth.py`
4. FastAPI docs/OpenAPI disabled at construction — `web/app.py build_fastapi_app()`
5. Content-Security-Policy headers (`script-src 'self'`, no unsafe-inline scripts) — `middleware/csp.py`

Do not weaken them.

## Known Gotchas

- `readme.md` / `project_context.md` are stale (describe the retired PyQt6 app) — trust this file and the code.
- The `DEEPGRAM_API_KEY` in `.env` returned 401 as of 2026-07-10 — rotate before live meeting tests.
- Haiku's minimum cacheable prefix is 4096 tokens — small context packs won't cache-hit early in a meeting (harmless).

## Design Context

- `PRODUCT.md` — design strategy: product register, web platform, single expert user, "Heads-Up Display for a live call" positioning, glance-first design principles, anti-references (no chatbot UI, no SaaS dashboard chrome).
- `DESIGN.md` — the visual system: Deep Space palette, Radar Blue primary, one-meaning-per-accent signal vocabulary, flat elevation ("glow means alive"), copilot card anatomy. Consult both before any UI work in `web/static/`.
