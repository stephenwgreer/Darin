"""FastAPI application factory.

Creates and wires:
- SSEEventBus (thread-safe callback → SSE bridge)
- AppController (framework-agnostic backend)
- FastAPI app with middleware, static files, and API routes

Security controls applied (DAR2-34):
  1. host=127.0.0.1  — set in main.py via uvicorn
  2. port=0          — set in main.py via uvicorn
  3. TokenAuthMiddleware on all routes
  4. FastAPI docs disabled (docs_url/redoc_url/openapi_url = None)
  5. CSPMiddleware on all responses
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import config as app_config
from app_controller import AppController
from middleware.csp import CSPMiddleware
from middleware.token_auth import TokenAuthMiddleware
from storage.meeting_store import MeetingStore
from web.api_router import create_router
from web.sse_event_bus import SSEEventBus

_STATIC_DIR = Path(__file__).parent / "static"


def configure_security(app: FastAPI, token: str) -> None:
    """Apply DAR2-34 localhost hardening controls to a FastAPI app.

    Controls applied here:
    - Control 3: Secret token middleware (validates ?token= on all routes)
    - Control 4: Disable FastAPI docs endpoints
    - Control 5: Content-Security-Policy headers

    Controls 1 (127.0.0.1) and 2 (port=0) are set in main.py.
    """
    app.docs_url = None
    app.redoc_url = None
    app.openapi_url = None
    app.add_middleware(TokenAuthMiddleware, token=token)
    app.add_middleware(CSPMiddleware)


def create_app(token: str) -> FastAPI:
    """Create and return the FastAPI app with all dependencies wired.

    Validates API keys, creates AppController + SSEEventBus, wires callbacks,
    mounts static files, registers routes, and applies security middleware.
    """
    app_config.validate_api_keys()

    from storage.app_config import AppConfigStore
    from pathlib import Path

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
        on_interim_transcript=lambda t: bus.put_event("interim_transcript", {"text": t}),
        on_final_transcript=lambda t: bus.put_event("final_transcript", {"text": t}),
    )
    controller.meeting_store = MeetingStore(base_dir=Path(app_cfg.storage_path))
    controller.on_meeting_state_change(lambda s: bus.put_event("state_change", {"state": s}))
    controller.on_timer_tick(lambda e: bus.put_event("timer_tick", {"elapsed": e}))

    # Test mode: bypass live audio when TEST_AUDIO_WAV env var is set
    test_wav_path = os.environ.get("TEST_AUDIO_WAV")
    if test_wav_path and os.path.exists(test_wav_path):
        from loguru import logger

        logger.info("Test mode: loading transcript from {}", test_wav_path)
        try:
            import scipy.io.wavfile as wavfile  # type: ignore[import-untyped]

            sample_rate, audio_data = wavfile.read(test_wav_path)
            transcript = controller.api_client.transcribe_with_deepgram(
                audio_data.tobytes(), sample_rate
            )
            controller.test_transcript = transcript
            logger.info("Test transcript loaded: {} chars", len(transcript))
        except Exception as e:  # noqa: BLE001
            from loguru import logger as _log

            _log.warning("Failed to load test WAV: {}", e)

    # Start continuous circular-buffer recording
    controller.start_recording()

    # Build FastAPI app
    fastapi_app = FastAPI()

    # Static files are token-exempt (JS/CSS must load before token is available)
    fastapi_app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Index route — served via explicit route so TokenAuthMiddleware applies
    @fastapi_app.get("/")
    async def index() -> HTMLResponse:
        html = (_STATIC_DIR / "index.html").read_text()
        return HTMLResponse(html)

    # API routes
    fastapi_app.include_router(create_router(bus, controller, app_cfg_store))

    # Security controls 3, 4, 5 (DAR2-34)
    configure_security(fastapi_app, token)

    return fastapi_app
