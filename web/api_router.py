"""FastAPI router: all REST and SSE endpoints for the vanilla-JS frontend.

All routes require ?token= (validated by TokenAuthMiddleware upstream).
The /api/events SSE endpoint is the server→browser push channel.
All POST endpoints are fire-and-forget — work runs in AppController threads.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app_controller import AppController
from prompts.registry import PROMPT_REGISTRY, get_prompt_config_by_id
from web.sse_event_bus import SSEEventBus


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class RunPromptBody(BaseModel):
    prompt_id: str


class RunPostMeetingPromptBody(BaseModel):
    prompt_id: str
    from_minute: int | None = None
    to_minute: int | None = None


class TranscribeLastNBody(BaseModel):
    seconds: int  # 30 or 60


class AskQuestionBody(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_router(bus: SSEEventBus, controller: AppController) -> APIRouter:
    """Build and return the API router wired to the given bus + controller."""
    router = APIRouter(prefix="/api")

    # ---- SSE stream -------------------------------------------------------

    @router.get("/events")
    async def sse_events() -> StreamingResponse:
        return StreamingResponse(
            bus.stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- Meeting lifecycle ------------------------------------------------

    @router.post("/start_meeting")
    async def start_meeting() -> dict[str, str]:
        await controller.start_meeting()
        return {"status": "ok"}

    @router.post("/stop_meeting")
    async def stop_meeting() -> dict[str, str]:
        await controller.stop_meeting()
        return {"status": "ok"}

    @router.post("/reset")
    async def reset() -> dict[str, str]:
        await controller.reset_to_idle()
        return {"status": "ok"}

    # ---- Prompt execution ------------------------------------------------

    @router.post("/run_prompt")
    async def run_prompt(body: RunPromptBody) -> dict[str, str]:
        cfg = get_prompt_config_by_id(body.prompt_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"Prompt not found: {body.prompt_id}")

        bus.reset()
        on_template_setup = bus.make_template_setup_callback(cfg.template_type, cfg.output_title)
        controller.run_prompt(cfg.template, on_template_setup=on_template_setup)
        return {"status": "ok"}

    @router.post("/run_post_meeting_prompt")
    async def run_post_meeting_prompt(body: RunPostMeetingPromptBody) -> dict[str, str]:
        cfg = get_prompt_config_by_id(body.prompt_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"Prompt not found: {body.prompt_id}")

        bus.reset()
        on_template_setup = bus.make_template_setup_callback(cfg.template_type, cfg.output_title)

        def on_complete(prompt_id: str, output_text: str) -> None:  # noqa: ARG001
            saved = controller.get_saved_analyses()
            bus.put_event(
                "saved_analyses",
                {"analyses": {pid: bool(txt) for pid, txt in saved.items()}},
            )

        controller.run_post_meeting_prompt(
            cfg,
            from_minute=body.from_minute,
            to_minute=body.to_minute,
            on_template_setup=on_template_setup,
            on_complete=on_complete,
        )
        return {"status": "ok"}

    # ---- Q&A --------------------------------------------------------------

    @router.post("/ask")
    async def ask(body: AskQuestionBody) -> dict[str, str]:
        if not body.question or not body.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        bus.reset()
        controller.ask_question(body.question)
        return {"status": "ok"}

    # ---- Capture ----------------------------------------------------------

    @router.post("/transcribe_last_n")
    async def transcribe_last_n(body: TranscribeLastNBody) -> dict[str, str]:
        controller.transcribe_last_n_seconds(body.seconds)
        return {"status": "ok"}

    # ---- Data queries -----------------------------------------------------

    @router.get("/state")
    async def get_state() -> dict[str, Any]:
        return {"state": controller.meeting_state, "elapsed": controller.elapsed_seconds}

    @router.get("/transcript")
    async def get_transcript() -> dict[str, Any]:
        return {"transcript": controller.get_meeting_transcript()}

    @router.get("/saved_analyses")
    async def get_saved_analyses() -> dict[str, Any]:
        saved = controller.get_saved_analyses()
        return {"analyses": {pid: bool(txt) for pid, txt in saved.items()}}

    @router.get("/prompts")
    async def get_prompts() -> dict[str, Any]:
        result: dict[str, list[dict[str, str]]] = {}
        for cfg in PROMPT_REGISTRY:
            bucket = cfg.bucket
            if bucket not in result:
                result[bucket] = []
            result[bucket].append(
                {
                    "id": cfg.id,
                    "button_text": cfg.button_text,
                    "output_title": cfg.output_title,
                    "template_type": cfg.template_type,
                }
            )
        return result

    return router
