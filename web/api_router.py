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
from storage.app_config import AppConfigStore, CustomPromptConfig
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


class SaveSettingsBody(BaseModel):
    storage_path: str


class CreateCustomPromptBody(BaseModel):
    button_text: str
    output_title: str
    template: str


class UpdatePromptBody(BaseModel):
    button_text: str | None = None
    output_title: str | None = None
    template: str | None = None


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_router(bus: SSEEventBus, controller: AppController, app_cfg_store: AppConfigStore) -> APIRouter:
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
        from prompts.registry import get_effective_registry
        cfg = app_cfg_store.load()
        registry = get_effective_registry(cfg)
        result: dict[str, list[dict[str, str]]] = {}
        for p in registry:
            bucket = p.bucket
            if bucket not in result:
                result[bucket] = []
            result[bucket].append(
                {
                    "id": p.id,
                    "button_text": p.button_text,
                    "output_title": p.output_title,
                    "template_type": p.template_type,
                }
            )
        return result

    # ---- Settings ---------------------------------------------------------

    @router.get("/settings")
    async def get_settings() -> dict:
        cfg = app_cfg_store.load()
        return {"storage_path": cfg.storage_path}

    @router.post("/settings")
    async def save_settings(body: SaveSettingsBody) -> dict:
        cfg = app_cfg_store.load()
        cfg.storage_path = body.storage_path
        app_cfg_store.save(cfg)
        return {"status": "ok"}

    @router.post("/pick_folder")
    async def pick_folder() -> dict:
        """Open native folder picker dialog. Requires display (tkinter)."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", 1)
            folder = filedialog.askdirectory(title="Select Meeting Storage Folder")
            root.destroy()
            return {"path": folder or None}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Folder picker unavailable: {e}") from e

    # ---- Meeting history --------------------------------------------------

    @router.get("/meetings")
    async def list_meetings() -> dict:
        if controller.meeting_store is None:
            return {"meetings": []}
        records = controller.meeting_store.list_meetings()
        result = []
        for r in records:
            result.append({
                "id": r.id,
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "duration_seconds": r.duration_seconds,
                "title": r.title,
            })
        return {"meetings": result}

    @router.get("/meetings/{meeting_id}/transcript")
    async def get_meeting_transcript(meeting_id: str) -> dict:
        if controller.meeting_store is None:
            raise HTTPException(status_code=404, detail="No store")
        record = controller.meeting_store.get_meeting(meeting_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Meeting not found")
        segments = [
            {"timestamp": seg.timestamp.isoformat(), "text": seg.text}
            for seg in record.segments
        ]
        return {
            "id": record.id,
            "title": record.title,
            "start_time": record.start_time.isoformat(),
            "end_time": record.end_time.isoformat() if record.end_time else None,
            "segments": segments,
        }

    @router.post("/meetings/{meeting_id}/ask")
    async def ask_about_meeting(meeting_id: str, body: AskQuestionBody) -> dict:
        if not body.question or not body.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        if controller.meeting_store is None:
            raise HTTPException(status_code=404, detail="No store")
        transcript = controller.meeting_store.get_full_transcript(meeting_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Meeting not found or empty")
        bus.reset()
        controller.ask_question(body.question, historical_transcript=transcript)
        return {"status": "ok"}

    # ---- Custom prompts CRUD ----------------------------------------------

    @router.get("/custom_prompts")
    async def get_custom_prompts() -> dict:
        cfg = app_cfg_store.load()
        from prompts.registry import get_effective_registry
        registry = get_effective_registry(cfg)
        return {
            "prompts": [
                {
                    "id": p.id,
                    "button_text": p.button_text,
                    "output_title": p.output_title,
                    "template": p.template,
                    "bucket": p.bucket,
                    "is_custom": p.bucket == "custom",
                }
                for p in registry
            ]
        }

    @router.post("/custom_prompts")
    async def create_custom_prompt(body: CreateCustomPromptBody) -> dict:
        import re
        import time
        cfg = app_cfg_store.load()
        slug = re.sub(r"[^a-z0-9]+", "_", body.button_text.lower()).strip("_")
        prompt_id = f"cp_{slug}_{int(time.time())}"
        cfg.custom_prompts.append(
            CustomPromptConfig(
                id=prompt_id,
                button_text=body.button_text,
                output_title=body.output_title,
                template=body.template,
            )
        )
        app_cfg_store.save(cfg)
        return {"id": prompt_id, "status": "ok"}

    @router.put("/custom_prompts/{prompt_id}")
    async def update_prompt(prompt_id: str, body: UpdatePromptBody) -> dict:
        cfg = app_cfg_store.load()

        # Check if it's a custom prompt
        custom = next((p for p in cfg.custom_prompts if p.id == prompt_id), None)
        if custom is not None:
            if body.button_text is not None:
                custom.button_text = body.button_text
            if body.output_title is not None:
                custom.output_title = body.output_title
            if body.template is not None:
                custom.template = body.template
            app_cfg_store.save(cfg)
            return {"status": "ok"}

        # Built-in override
        builtin = next((p for p in PROMPT_REGISTRY if p.id == prompt_id), None)
        if builtin is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        overrides = cfg.prompt_overrides.setdefault(prompt_id, {})
        if body.button_text is not None:
            overrides["button_text"] = body.button_text
        if body.output_title is not None:
            overrides["output_title"] = body.output_title
        if body.template is not None:
            overrides["template"] = body.template
        app_cfg_store.save(cfg)
        return {"status": "ok"}

    @router.delete("/custom_prompts/{prompt_id}")
    async def delete_prompt(prompt_id: str) -> dict:
        cfg = app_cfg_store.load()

        # Remove from custom prompts
        before = len(cfg.custom_prompts)
        cfg.custom_prompts = [p for p in cfg.custom_prompts if p.id != prompt_id]
        if len(cfg.custom_prompts) < before:
            app_cfg_store.save(cfg)
            return {"status": "ok"}

        # Mark built-in as deleted
        builtin = next((p for p in PROMPT_REGISTRY if p.id == prompt_id), None)
        if builtin is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        if prompt_id not in cfg.deleted_prompt_ids:
            cfg.deleted_prompt_ids.append(prompt_id)
        # Clear any overrides for deleted prompts
        cfg.prompt_overrides.pop(prompt_id, None)
        app_cfg_store.save(cfg)
        return {"status": "ok"}

    return router
