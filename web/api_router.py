"""FastAPI router: all REST and SSE endpoints for the vanilla-JS frontend.

All routes require ?token= (validated by TokenAuthMiddleware upstream).
The /api/events SSE endpoint is the server→browser push channel (multi-client
fan-out — each connected tab gets its own queue).

All blocking work (controller start/stop, buffer slicing, config file I/O,
meeting-store reads, the tkinter folder picker) runs via asyncio.to_thread so
the event loop — and therefore SSE delivery — never stalls.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app_controller import AppController, MeetingAlreadyActiveError, MeetingStartError
from prompts.registry import (
    PROMPT_REGISTRY,
    PromptConfig,
    get_effective_registry,
    get_prompt_config_by_id,
)
from prompts.templates import PERSONAS
from services.context_pack import ContextPack
from storage.app_config import AppConfigStore, CustomPromptConfig
from storage.meeting_store import MeetingStore
from web.sse_event_bus import SSEEventBus


# ---------------------------------------------------------------------------
# Path-parameter validation
# ---------------------------------------------------------------------------

# Meeting ids are strftime-based ("2026-07-09_141323", optional "_N" suffix);
# card ids are "card_<12 hex>". A strict shared allowlist rejects traversal
# ("../"), separators, and anything else that could escape the store directory.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _validate_path_id(value: str, *, kind: str) -> None:
    """Reject path params that don't match the strict id allowlist."""
    if not _SAFE_ID_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {kind}")


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
    background_style: str = "default"


class ContextPackBody(BaseModel):
    profile: str | None = None
    products: str | None = None
    known_issues: str | None = None


class PersonaBody(BaseModel):
    persona: str


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


def create_router(
    bus: SSEEventBus, controller: AppController, app_cfg_store: AppConfigStore
) -> APIRouter:
    """Build and return the API router wired to the given bus + controller."""
    router = APIRouter(prefix="/api")

    def _resolve_prompt(prompt_id: str) -> PromptConfig | None:
        """Resolve a prompt id against the effective registry (built-ins with
        overrides + custom prompts) and the off-registry 'ask' config.

        Blocking (config file read) — call via asyncio.to_thread.
        """
        cfg = app_cfg_store.load()
        for p in get_effective_registry(cfg):
            if p.id == prompt_id:
                return p
        return get_prompt_config_by_id(prompt_id)

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
        try:
            await controller.start_meeting()
        except MeetingAlreadyActiveError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except MeetingStartError as e:
            # Capture/transcription failed to start — nothing is recording, so
            # the client must NOT be told the session is live.
            raise HTTPException(status_code=503, detail=str(e)) from e
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
        cfg = await asyncio.to_thread(_resolve_prompt, body.prompt_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"Prompt not found: {body.prompt_id}")

        # Reactive/custom card prompts → forced-tool-use card lane
        if cfg.template_type == "card":
            accepted = await asyncio.to_thread(controller.run_reactive_prompt, cfg)
            if not accepted:
                raise HTTPException(status_code=409, detail=f"Prompt already in flight: {cfg.id}")
            return {"status": "ok"}

        # Legacy long-form streaming path (post-meeting-style templates).
        # NO bus.reset() here: stream state is (re)installed by the
        # on_template_setup callback only AFTER the controller ACCEPTS the
        # request — a rejected duplicate must never clobber an in-flight stream.
        on_template_setup = bus.make_template_setup_callback(cfg.template_type, cfg.output_title)
        accepted = await asyncio.to_thread(
            controller.run_prompt,
            cfg.template,
            prompt_id=cfg.id,
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            on_template_setup=on_template_setup,
        )
        if not accepted:
            raise HTTPException(status_code=409, detail="Another analysis is already streaming")
        return {"status": "ok"}

    @router.post("/run_post_meeting_prompt")
    async def run_post_meeting_prompt(body: RunPostMeetingPromptBody) -> dict[str, str]:
        cfg = await asyncio.to_thread(_resolve_prompt, body.prompt_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"Prompt not found: {body.prompt_id}")

        # NO bus.reset() here — see /run_prompt: stream state is installed by
        # on_template_setup only after the controller accepts the request.
        on_template_setup = bus.make_template_setup_callback(cfg.template_type, cfg.output_title)

        def on_complete(prompt_id: str, output_text: str) -> None:  # noqa: ARG001
            saved = controller.get_saved_analyses()
            bus.put_event(
                "saved_analyses",
                {"analyses": {pid: bool(txt) for pid, txt in saved.items()}},
            )

        accepted = await asyncio.to_thread(
            controller.run_post_meeting_prompt,
            cfg,
            from_minute=body.from_minute,
            to_minute=body.to_minute,
            on_template_setup=on_template_setup,
            on_complete=on_complete,
        )
        if not accepted:
            raise HTTPException(status_code=409, detail="Another analysis is already streaming")
        return {"status": "ok"}

    # ---- Q&A --------------------------------------------------------------

    @router.post("/ask")
    async def ask(body: AskQuestionBody) -> dict[str, str]:
        if not body.question or not body.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        accepted = await asyncio.to_thread(controller.ask_question, body.question)
        if not accepted:
            raise HTTPException(status_code=409, detail="A question is already in flight")
        return {"status": "ok"}

    # ---- Capture ----------------------------------------------------------

    @router.post("/transcribe_last_n")
    async def transcribe_last_n(body: TranscribeLastNBody) -> dict[str, str]:
        if not 0 < body.seconds <= 600:
            raise HTTPException(status_code=400, detail="seconds must be between 1 and 600")
        # Buffer slicing (deque snapshot + mono mix) is CPU/lock work — off-loop.
        await asyncio.to_thread(controller.transcribe_last_n_seconds, body.seconds)
        return {"status": "ok"}

    # ---- Cards -------------------------------------------------------------

    @router.post("/cards/{card_id}/dismiss")
    async def dismiss_card(card_id: str) -> dict[str, str]:
        _validate_path_id(card_id, kind="card id")
        found = await asyncio.to_thread(controller.dismiss_card, card_id)
        if not found:
            raise HTTPException(status_code=404, detail="Card not found")
        return {"status": "ok"}

    # ---- Context pack ------------------------------------------------------

    @router.get("/context")
    async def get_context() -> dict[str, str]:
        pack: ContextPack | None = controller.context_pack
        if pack is None:
            raise HTTPException(status_code=503, detail="Context pack unavailable")
        return await asyncio.to_thread(pack.load)

    @router.put("/context")
    async def put_context(body: ContextPackBody) -> dict[str, str]:
        pack: ContextPack | None = controller.context_pack
        if pack is None:
            raise HTTPException(status_code=503, detail="Context pack unavailable")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await asyncio.to_thread(lambda: pack.save(**updates))
        return {"status": "ok"}

    # ---- Persona -----------------------------------------------------------

    @router.get("/persona")
    async def get_persona() -> dict[str, str]:
        return {"persona": controller.persona}

    @router.post("/persona")
    async def set_persona(body: PersonaBody) -> dict[str, str]:
        if body.persona not in PERSONAS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid persona: must be one of {', '.join(PERSONAS)}",
            )
        controller.persona = body.persona

        def _persist() -> None:
            cfg = app_cfg_store.load()
            cfg.persona = body.persona
            app_cfg_store.save(cfg)

        await asyncio.to_thread(_persist)
        return {"status": "ok", "persona": body.persona}

    # ---- Data queries -----------------------------------------------------

    @router.get("/state")
    async def get_state() -> dict[str, Any]:
        return {"state": controller.meeting_state, "elapsed": controller.elapsed_seconds}

    @router.get("/transcript")
    async def get_transcript() -> dict[str, Any]:
        return {"transcript": await asyncio.to_thread(controller.get_meeting_transcript)}

    @router.get("/saved_analyses")
    async def get_saved_analyses() -> dict[str, Any]:
        saved = await asyncio.to_thread(controller.get_saved_analyses)
        return {"analyses": {pid: bool(txt) for pid, txt in saved.items()}}

    @router.get("/prompts")
    async def get_prompts() -> dict[str, Any]:
        registry = await asyncio.to_thread(lambda: get_effective_registry(app_cfg_store.load()))
        # New registry grouping — all three groups always present.
        result: dict[str, list[dict[str, str]]] = {
            "reactive": [],
            "post_meeting": [],
            "custom": [],
        }
        for p in registry:
            result.setdefault(p.bucket, []).append(
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
        cfg = await asyncio.to_thread(app_cfg_store.load)
        return {"storage_path": cfg.storage_path, "background_style": cfg.background_style}

    @router.post("/settings")
    async def save_settings(body: SaveSettingsBody) -> dict:
        path = Path(body.storage_path)
        if not path.is_absolute():
            raise HTTPException(status_code=400, detail="storage_path must be an absolute path")

        cfg = await asyncio.to_thread(app_cfg_store.load)
        path_changed = body.storage_path != cfg.storage_path

        if path_changed and controller.meeting_state == "active":
            raise HTTPException(
                status_code=409,
                detail="Cannot change the storage folder while a meeting is active",
            )

        if path_changed:
            # Rebind MeetingStore + ContextPack LIVE — no restart needed.
            def _rebind() -> None:
                controller.meeting_store = MeetingStore(base_dir=path)
                controller.context_pack = ContextPack(path)

            try:
                await asyncio.to_thread(_rebind)
            except OSError as e:
                raise HTTPException(
                    status_code=400, detail=f"Storage folder is not usable: {e}"
                ) from e

        cfg.storage_path = body.storage_path
        if body.background_style in ("default", "darin"):
            cfg.background_style = body.background_style
        await asyncio.to_thread(app_cfg_store.save, cfg)
        return {"status": "ok"}

    @router.post("/pick_folder")
    async def pick_folder() -> dict:
        """Open native folder picker dialog. Requires display (tkinter)."""

        def _pick() -> str | None:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", 1)
            try:
                return filedialog.askdirectory(title="Select Meeting Storage Folder") or None
            finally:
                root.destroy()

        try:
            # Modal tkinter dialog blocks until dismissed — must run off-loop.
            folder = await asyncio.to_thread(_pick)
            return {"path": folder}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Folder picker unavailable: {e}") from e

    # ---- Meeting history --------------------------------------------------

    @router.get("/meetings")
    async def list_meetings() -> dict:
        if controller.meeting_store is None:
            return {"meetings": []}
        records = await asyncio.to_thread(controller.meeting_store.list_meetings)
        result = []
        for r in records:
            result.append(
                {
                    "id": r.id,
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "duration_seconds": r.duration_seconds,
                    "title": r.title,
                }
            )
        return {"meetings": result}

    @router.get("/meetings/{meeting_id}/transcript")
    async def get_meeting_transcript(meeting_id: str) -> dict:
        _validate_path_id(meeting_id, kind="meeting id")
        if controller.meeting_store is None:
            raise HTTPException(status_code=404, detail="No store")
        record = await asyncio.to_thread(controller.meeting_store.get_meeting, meeting_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Meeting not found")
        segments = [
            {"timestamp": seg.timestamp.isoformat(), "text": seg.text} for seg in record.segments
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
        _validate_path_id(meeting_id, kind="meeting id")
        if not body.question or not body.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        if controller.meeting_store is None:
            raise HTTPException(status_code=404, detail="No store")
        transcript = await asyncio.to_thread(
            controller.meeting_store.get_full_transcript, meeting_id
        )
        if not transcript:
            raise HTTPException(status_code=404, detail="Meeting not found or empty")
        accepted = await asyncio.to_thread(
            controller.ask_question, body.question, historical_transcript=transcript
        )
        if not accepted:
            raise HTTPException(status_code=409, detail="A question is already in flight")
        return {"status": "ok"}

    # ---- Custom prompts CRUD ----------------------------------------------

    @router.get("/custom_prompts")
    async def get_custom_prompts() -> dict:
        registry = await asyncio.to_thread(lambda: get_effective_registry(app_cfg_store.load()))
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
        slug = re.sub(r"[^a-z0-9]+", "_", body.button_text.lower()).strip("_")
        prompt_id = f"cp_{slug}_{int(time.time())}"

        def _create() -> None:
            cfg = app_cfg_store.load()
            cfg.custom_prompts.append(
                CustomPromptConfig(
                    id=prompt_id,
                    button_text=body.button_text,
                    output_title=body.output_title,
                    template=body.template,
                )
            )
            app_cfg_store.save(cfg)

        await asyncio.to_thread(_create)
        return {"id": prompt_id, "status": "ok"}

    @router.put("/custom_prompts/{prompt_id}")
    async def update_prompt(prompt_id: str, body: UpdatePromptBody) -> dict:
        _validate_path_id(prompt_id, kind="prompt id")

        def _update() -> bool:
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
                return True

            # Built-in override
            builtin = next((p for p in PROMPT_REGISTRY if p.id == prompt_id), None)
            if builtin is None:
                return False
            overrides = cfg.prompt_overrides.setdefault(prompt_id, {})
            if body.button_text is not None:
                overrides["button_text"] = body.button_text
            if body.output_title is not None:
                overrides["output_title"] = body.output_title
            if body.template is not None:
                overrides["template"] = body.template
            app_cfg_store.save(cfg)
            return True

        found = await asyncio.to_thread(_update)
        if not found:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"status": "ok"}

    @router.delete("/custom_prompts/{prompt_id}")
    async def delete_prompt(prompt_id: str) -> dict:
        _validate_path_id(prompt_id, kind="prompt id")

        def _delete() -> bool:
            cfg = app_cfg_store.load()

            # Remove from custom prompts
            before = len(cfg.custom_prompts)
            cfg.custom_prompts = [p for p in cfg.custom_prompts if p.id != prompt_id]
            if len(cfg.custom_prompts) < before:
                app_cfg_store.save(cfg)
                return True

            # Mark built-in as deleted
            builtin = next((p for p in PROMPT_REGISTRY if p.id == prompt_id), None)
            if builtin is None:
                return False
            if prompt_id not in cfg.deleted_prompt_ids:
                cfg.deleted_prompt_ids.append(prompt_id)
            # Clear any overrides for deleted prompts
            cfg.prompt_overrides.pop(prompt_id, None)
            app_cfg_store.save(cfg)
            return True

        found = await asyncio.to_thread(_delete)
        if not found:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"status": "ok"}

    return router
