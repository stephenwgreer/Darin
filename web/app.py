"""FastAPI application factory.

Creates and wires:
- SSEEventBus (multi-client thread-safe callback → SSE bridge)
- AppController (framework-agnostic backend)
- FastAPI app with middleware, static files, and API routes

Security controls applied (DAR2-34):
  1. host=127.0.0.1  — set in main.py via uvicorn
  2. port=0          — set in main.py via uvicorn
  3. TokenAuthMiddleware on all routes
  4. FastAPI docs disabled at CONSTRUCTION time (docs_url/redoc_url/
     openapi_url passed to FastAPI(...) — assigning the attributes after
     construction is a no-op because the docs routes are registered inside
     FastAPI.__init__)
  5. CSPMiddleware on all responses
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

import config as app_config
from api.providers import ModelRegistry
from app_controller import AppController
from middleware.csp import CSPMiddleware
from middleware.token_auth import TokenAuthMiddleware
from services.context_pack import ContextPack
from services.knowledge_base import KnowledgeBase
from storage.app_config import AppConfigStore
from storage.meeting_store import MeetingStore
from web.api_router import create_router
from web.sse_event_bus import SSEEventBus


_STATIC_DIR = Path(__file__).parent / "static"


def build_fastapi_app(lifespan=None) -> FastAPI:  # noqa: ANN001 — Starlette lifespan factory
    """Construct the bare FastAPI instance with docs disabled (Control 4).

    docs_url/redoc_url/openapi_url MUST be passed to the constructor —
    the docs routes are registered inside FastAPI.__init__, so setting the
    attributes afterwards does nothing.
    """
    return FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


def configure_security(app: FastAPI, token: str) -> None:
    """Apply DAR2-34 localhost hardening middleware to a FastAPI app.

    Controls applied here:
    - Control 3: Secret token middleware (validates ?token= on all routes)
    - Control 5: Content-Security-Policy headers

    Control 4 (docs disabled) lives in build_fastapi_app(); Controls 1
    (127.0.0.1) and 2 (port=0) are set in main.py.
    """
    app.add_middleware(TokenAuthMiddleware, token=token)
    app.add_middleware(CSPMiddleware)


def _load_test_transcript(controller: AppController, test_wav_path: str) -> None:
    """Test mode: transcribe a fixture WAV so prompts work without live audio."""
    logger.info("Test mode: loading transcript from {}", test_wav_path)
    try:
        import soundfile as sf

        audio_data, sample_rate = sf.read(test_wav_path, dtype="int16")
        transcript = controller.api_client.transcribe_with_deepgram(audio_data, sample_rate)
        controller.test_transcript = transcript
        logger.info("Test transcript loaded: {} chars", len(transcript))
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to load test WAV: {}", e)


def create_app(token: str) -> FastAPI:
    """Create and return the FastAPI app with all dependencies wired.

    Validates API keys, creates AppController + SSEEventBus, wires callbacks,
    mounts static files, registers routes, and applies security middleware.

    Capture is session-scoped: recording starts with POST /start_meeting,
    never at app boot (owner requirement — nothing records automatically).
    """
    app_config.validate_api_keys()

    app_cfg_store = AppConfigStore()
    app_cfg = app_cfg_store.load()

    bus = SSEEventBus()

    controller = AppController(
        on_transcription_complete=lambda t: bus.put_event(
            "transcription_complete", {"transcript": t}
        ),
        on_processing_complete=lambda r: bus.put_event("processing_complete", r),
        on_progress=lambda m: bus.put_event("progress", {"message": m}),
        on_stream_chunk=bus.handle_stream_chunk,
        on_interim_transcript=lambda t, s: bus.put_event(
            "interim_transcript", {"text": t, "speaker": s}
        ),
        on_final_transcript=lambda t, s: bus.put_event(
            "final_transcript", {"text": t, "speaker": s}
        ),
    )
    controller.meeting_store = MeetingStore(base_dir=Path(app_cfg.storage_path))
    # F2: resolve per-prompt model ids to providers so custom OpenAI-compatible
    # endpoints route through the adapter; refreshed live on settings save.
    controller.api_client.model_registry = ModelRegistry(app_cfg)
    controller.watcher_model = app_cfg.watcher_model
    controller.auto_answer_enabled = app_cfg.auto_answer_enabled
    controller.on_meeting_state_change(lambda s: bus.put_event("state_change", {"state": s}))
    controller.on_timer_tick(lambda e: bus.put_event("timer_tick", {"elapsed": e}))

    # Copilot engine wiring (Wave 2): context pack, persona, card/usage events
    controller.context_pack = ContextPack(Path(app_cfg.storage_path))
    # SAS knowledge base (RAG): retrieval grounding for reactive/Ask/auto-answer.
    # Ingest progress fans out to the UI as "kb_ingest" SSE events.
    controller.knowledge_base = KnowledgeBase(
        Path(app_cfg.storage_path),
        enabled=app_cfg.knowledge_base_enabled,
        docs_folder=app_cfg.knowledge_docs_folder,
        on_progress=lambda ev: bus.put_event("kb_ingest", ev),
    )
    controller.persona = app_cfg.persona
    controller.on_card = lambda card: bus.put_event("card", card)
    controller.on_card_dismissed = lambda card_id: bus.put_event("card_dismissed", {"id": card_id})
    controller.on_watcher_status = lambda state: bus.put_event("watcher_status", {"state": state})
    controller.on_usage = lambda data: bus.put_event("usage", data)
    # Component failures (device death, streaming errors, failed session start)
    # surface to the UI as an "error" SSE event instead of dying in the logs.
    controller.on_error = lambda msg: bus.put_event("error", {"message": msg})

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
        # Bind the running loop so worker threads can fan events out to SSE
        # clients via call_soon_threadsafe even before the first client connects.
        bus.bind_loop(asyncio.get_running_loop())

        # Test mode: bypass live audio when TEST_AUDIO_WAV env var is set.
        # Runs off-loop (Deepgram REST call) so startup never blocks serving.
        test_wav_path = os.environ.get("TEST_AUDIO_WAV")
        if test_wav_path and os.path.exists(test_wav_path):
            await asyncio.to_thread(_load_test_transcript, controller, test_wav_path)

        # Warm the embedder once so the first grounded query isn't cold — only
        # when there's an index to serve. Fire-and-forget + fail-soft: a missing
        # rag extra or a failed model download must never block or break startup.
        kb = controller.knowledge_base
        if kb is not None and not kb.is_empty:

            async def _warmup_kb() -> None:
                try:
                    await asyncio.to_thread(kb.warmup)
                except Exception as e:  # noqa: BLE001 — warmup must never break boot
                    logger.warning("Knowledge base warmup failed: {}", e)

            asyncio.create_task(_warmup_kb())

        yield

        bus.close()

    # Build FastAPI app — docs disabled at construction (Control 4)
    fastapi_app = build_fastapi_app(lifespan=lifespan)

    # Static files are token-exempt (JS/CSS must load before token is available)
    fastapi_app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Index route — served via explicit route so TokenAuthMiddleware applies
    @fastapi_app.get("/")
    async def index() -> HTMLResponse:
        html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    # API routes
    fastapi_app.include_router(create_router(bus, controller, app_cfg_store))

    # Security controls 3 and 5 (DAR2-34)
    configure_security(fastapi_app, token)

    # Expose the controller for tests/diagnostics (session-scoped capture
    # invariant: nothing may be recording at boot).
    fastapi_app.state.controller = controller

    return fastapi_app
