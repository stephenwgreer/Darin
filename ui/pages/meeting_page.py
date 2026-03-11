"""NiceGUI meeting page — top-level layout (DAR2-26).

Registers the "/" route with NiceGUI. Creates all five components
and wires AppController callbacks to them.

Key principle: raw Deepgram transcript is NEVER displayed.
Output panel shows only Claude analysis results.
"""

from __future__ import annotations

from loguru import logger
from nicegui import Client, ui

from app_controller import AppController
from ui.components.capture_buttons import CaptureButtons
from ui.components.meeting_controls import MeetingControls
from ui.components.output_panel import OutputPanel
from ui.components.prompt_buttons import PromptButtons


def create_meeting_page(controller: AppController) -> None:
    """Register the NiceGUI meeting page. Called once at app startup."""

    @ui.page("/")
    async def meeting_page(client: Client) -> None:
        # All state lives in AppController — page reads it, never owns it.

        with ui.column().classes("w-full max-w-4xl mx-auto gap-4 p-4"):
            # Header
            ui.label("DARIN").classes("text-2xl font-bold")

            # Meeting controls (start/stop + pulsing indicator + timer)
            controls = MeetingControls(controller)

            # Bounded capture (Last 30s / Last 1m — always available)
            CaptureButtons(controller)

            # Claude analysis output panel (created before PromptButtons so the
            # reference can be passed in for on_template_setup wiring)
            output = OutputPanel(controller, client=client)

            # Context-aware prompt buttons
            prompts = PromptButtons(controller, output_panel=output)

        # Wire AppController state changes to components
        controller.on_meeting_state_change(
            lambda state: _handle_state_change(state, controls, prompts)
        )
        controller.on_timer_tick(lambda elapsed: controls.update_timer(elapsed))


def _handle_state_change(
    state: str,
    controls: MeetingControls,
    prompts: PromptButtons,
) -> None:
    """Dispatch state changes to component methods."""
    try:
        controls.set_state(state)
    except Exception:
        logger.exception("controls.set_state failed for state=%r", state)
    try:
        prompts.set_state(state)
    except Exception:
        logger.exception("prompts.set_state failed for state=%r", state)
