"""Context-aware prompt buttons (DAR2-26).

Mid-meeting prompts (MEETING_ACTIVE only):
- Problem-solving, evaluate, analyze, first principles, hypothesis

Post-meeting prompts (POST_MEETING only):
- Meeting summary, extract topics, action items, key decisions

Copy Transcript button (POST_MEETING only):
- Copies full meeting transcript to clipboard via navigator.clipboard API

Processing guard: all prompt buttons disabled while a prompt is executing.
"""

from __future__ import annotations

import json

from nicegui import ui


class PromptButtons:
    """Context-aware prompt buttons with processing guard."""

    def __init__(self, controller: object) -> None:
        self._controller = controller
        self._prompt_buttons: list[ui.button] = []

        # Mid-meeting prompts (hidden by default)
        with ui.card().classes("w-full") as self._mid_meeting_card:
            ui.label("Meeting Analysis").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.row().classes("gap-2 flex-wrap"):
                for name, template in self._mid_meeting_prompts():
                    btn = ui.button(
                        name,
                        on_click=lambda t=template: self._run_prompt(t),
                    ).classes("bg-blue-600 text-white")
                    self._prompt_buttons.append(btn)
        self._mid_meeting_card.set_visibility(False)

        # Post-meeting prompts (hidden by default)
        with ui.card().classes("w-full") as self._post_meeting_card:
            ui.label("Post-Meeting Analysis").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.row().classes("gap-2 flex-wrap"):
                for name, template in self._post_meeting_prompts():
                    btn = ui.button(
                        name,
                        on_click=lambda t=template: self._run_prompt(t),
                    ).classes("bg-purple-600 text-white")
                    self._prompt_buttons.append(btn)

                # Copy Transcript button
                self._copy_btn = ui.button(
                    "Copy Transcript",
                    on_click=self._copy_transcript,
                    icon="content_copy",
                ).classes("bg-gray-600 text-white")
        self._post_meeting_card.set_visibility(False)

    async def _run_prompt(self, template: str) -> None:
        """Run prompt with processing guard — disables all prompt buttons."""
        self._set_buttons_enabled(False)
        try:
            self._controller.run_prompt(template)  # type: ignore[attr-defined]
        finally:
            self._set_buttons_enabled(True)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable all prompt buttons."""
        for btn in self._prompt_buttons:
            btn.set_enabled(enabled)

    async def _copy_transcript(self) -> None:
        """Copy full meeting transcript to clipboard (json.dumps for JS safety)."""
        transcript = self._controller.get_meeting_transcript()  # type: ignore[attr-defined]
        if transcript:
            await ui.run_javascript(
                f"navigator.clipboard.writeText({json.dumps(transcript)})"
            )
            ui.notify("Transcript copied to clipboard", type="positive")
        else:
            ui.notify("No transcript available", type="warning")

    def set_state(self, state: str) -> None:
        """Show/hide prompt cards based on meeting state."""
        self._mid_meeting_card.set_visibility(state == "active")
        self._post_meeting_card.set_visibility(state == "post_meeting")

    @staticmethod
    def _mid_meeting_prompts() -> list[tuple[str, str]]:
        """Prompts available during active meeting."""
        return [
            ("Evaluate Problem", "evaluate_problem"),
            ("Analyze Statement", "analyze_statement"),
            ("First Principles", "first_principles"),
            ("Hypothesis", "hypothesis"),
        ]

    @staticmethod
    def _post_meeting_prompts() -> list[tuple[str, str]]:
        """Prompts available after meeting ends."""
        return [
            ("Meeting Summary", "meeting_summary"),
            ("Extract Topics", "extract_topics"),
            ("Action Items", "action_items"),
            ("Key Decisions", "key_decisions"),
        ]
