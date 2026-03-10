"""Context-aware prompt buttons — three-bucket layout (DAR2-27).

Bucket 1 — Meeting Analysis (blue, MEETING_ACTIVE only):
    9 mid-meeting prompts driven from registry bucket="mid_meeting"

Bucket 2 — Reasoning Frameworks (amber, MEETING_ACTIVE only):
    5 prompts driven from registry bucket="reasoning"

Bucket 3 — Post-Meeting Analysis (purple, POST_MEETING only):
    4 prompts driven from registry bucket="post_meeting"
    Includes segment selector, checkmark badges, and Copy Transcript.

Processing guard: all prompt buttons disabled while any prompt is executing.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from nicegui import ui

from prompts.registry import PROMPT_REGISTRY, PromptConfig, get_prompts_by_bucket


_TEMPLATE_TO_TYPE: dict[str, str] = {cfg.template: cfg.template_type for cfg in PROMPT_REGISTRY}


class PromptButtons:
    """Context-aware prompt buttons with three-bucket layout and processing guard."""

    def __init__(self, controller: object, output_panel: object | None = None) -> None:
        self._controller = controller
        self._output_panel = output_panel
        self._prompt_buttons: list[ui.button] = []
        self._post_meeting_badges: dict[str, ui.badge] = {}

        # --- Bucket 1: Meeting Analysis card (blue, MEETING_ACTIVE only) ---
        with ui.card().classes("w-full") as self._mid_meeting_card:
            ui.label("Meeting Analysis").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.row().classes("gap-2 flex-wrap"):
                for cfg in get_prompts_by_bucket("mid_meeting"):
                    btn = ui.button(
                        cfg.button_text,
                        on_click=lambda c=cfg: self._run_mid_meeting(c),
                    ).classes("bg-blue-600 text-white")
                    self._prompt_buttons.append(btn)
        self._mid_meeting_card.set_visibility(False)

        # --- Bucket 2: Reasoning Frameworks card (amber, MEETING_ACTIVE only) ---
        with ui.card().classes("w-full") as self._reasoning_card:
            ui.label("Reasoning Frameworks").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.row().classes("gap-2 flex-wrap"):
                for cfg in get_prompts_by_bucket("reasoning"):
                    btn = ui.button(
                        cfg.button_text,
                        on_click=lambda c=cfg: self._run_mid_meeting(c),
                    ).classes("bg-amber-600 text-white")
                    self._prompt_buttons.append(btn)
        self._reasoning_card.set_visibility(False)

        # --- Bucket 3: Post-Meeting Analysis card (purple, POST_MEETING only) ---
        with ui.card().classes("w-full") as self._post_meeting_card:
            ui.label("Post-Meeting Analysis").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )

            # Segment selector row
            with ui.row().classes("gap-2 items-center"):
                ui.label("Analyze:").classes("text-sm")
                self._segment_mode = ui.select(
                    ["Full transcript", "Time range"],
                    value="Full transcript",
                    on_change=self._on_segment_mode_change,
                ).classes("text-sm")

            with ui.row().classes("gap-2 items-center") as self._range_row:
                ui.label("From min").classes("text-sm")
                self._from_minute = ui.number(min=0, value=0).classes("w-16")
                ui.label("to min").classes("text-sm")
                self._to_minute = ui.number(min=1, value=60).classes("w-16")
            self._range_row.set_visibility(False)

            # Post-meeting prompt buttons with checkmark badges
            with ui.row().classes("gap-2 flex-wrap"):
                for cfg in get_prompts_by_bucket("post_meeting"):
                    with ui.element("div").classes("relative") as _container:
                        btn = ui.button(
                            cfg.button_text,
                            on_click=lambda c=cfg: self._run_post_meeting(c),
                        ).classes("bg-purple-600 text-white")
                        badge = ui.badge("✓").classes("absolute -top-1 -right-1 hidden")
                    self._prompt_buttons.append(btn)
                    self._post_meeting_badges[cfg.id] = badge

                # Copy Transcript utility button
                self._copy_btn = ui.button(
                    "Copy Transcript",
                    on_click=self._copy_transcript,
                    icon="content_copy",
                ).classes("bg-gray-600 text-white")
        self._post_meeting_card.set_visibility(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_template_setup(self, prompt_template: str) -> Callable[[str], str | None] | None:
        """Create the on_template_setup callback for a prompt template."""
        if self._output_panel is None:
            return None

        def on_template_setup(pt: str) -> str | None:
            template_type = _TEMPLATE_TO_TYPE.get(pt)
            if template_type and self._output_panel is not None:
                self._output_panel.setup_template(template_type)  # type: ignore[attr-defined]
            return template_type

        return on_template_setup

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable all prompt buttons (processing guard)."""
        for btn in self._prompt_buttons:
            btn.set_enabled(enabled)

    def _mark_as_run(self, prompt_id: str) -> None:
        """Show the checkmark badge on a post-meeting button."""
        badge = self._post_meeting_badges.get(prompt_id)
        if badge is not None:
            badge.set_visibility(True)
            badge.classes(remove="hidden")

    def _refresh_saved_state(self) -> None:
        """Update badge visibility based on which analyses have saved results."""
        analyses = self._controller.get_saved_analyses()  # type: ignore[attr-defined]
        for prompt_id, badge in self._post_meeting_badges.items():
            is_saved = prompt_id in analyses
            badge.set_visibility(is_saved)
            if is_saved:
                badge.classes(remove="hidden")
            else:
                badge.classes(add="hidden")

    def _on_segment_mode_change(self, event: object) -> None:
        """Show/hide minute range inputs based on segment mode selection."""
        self._range_row.set_visibility(self._segment_mode.value == "Time range")

    # ------------------------------------------------------------------
    # Prompt execution
    # ------------------------------------------------------------------

    async def _run_mid_meeting(self, cfg: PromptConfig) -> None:
        """Run a mid-meeting or reasoning prompt against bounded audio capture."""
        self._set_buttons_enabled(False)
        self._controller.run_prompt(  # type: ignore[attr-defined]
            cfg.template,
            on_template_setup=self._make_template_setup(cfg.template),
        )
        self._set_buttons_enabled(True)

    async def _run_post_meeting(self, cfg: PromptConfig) -> None:
        """Run a post-meeting prompt against the stored transcript."""
        from_minute = None
        to_minute = None
        if self._segment_mode.value == "Time range":
            from_minute = int(self._from_minute.value)
            to_minute = int(self._to_minute.value)
            if from_minute >= to_minute:
                ui.notify("'From' must be less than 'To'", type="warning")
                return

        self._set_buttons_enabled(False)
        self._controller.run_post_meeting_prompt(  # type: ignore[attr-defined]
            cfg,
            from_minute=from_minute,
            to_minute=to_minute,
            on_template_setup=self._make_template_setup(cfg.template),
            on_complete=lambda prompt_id, text: self._on_post_meeting_complete(prompt_id, text),
        )

    def _on_post_meeting_complete(self, prompt_id: str, text: str) -> None:
        """Re-enable buttons and mark the prompt as run after streaming finishes."""
        self._set_buttons_enabled(True)
        self._mark_as_run(prompt_id)

    async def _copy_transcript(self) -> None:
        """Copy full meeting transcript to clipboard (json.dumps for JS safety)."""
        transcript = self._controller.get_meeting_transcript()  # type: ignore[attr-defined]
        if transcript:
            await ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(transcript)})")
            ui.notify("Transcript copied to clipboard", type="positive")
        else:
            ui.notify("No transcript available", type="warning")

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Show/hide prompt cards based on meeting state."""
        is_active = state == "active"
        is_post = state == "post_meeting"

        self._mid_meeting_card.set_visibility(is_active)
        self._reasoning_card.set_visibility(is_active)
        self._post_meeting_card.set_visibility(is_post)

        if is_post:
            self._refresh_saved_state()
