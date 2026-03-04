"""Start/Stop meeting buttons, pulsing indicator, and elapsed timer (DAR2-26)."""

from __future__ import annotations

from nicegui import ui


class MeetingControls:
    """Start/Stop meeting buttons and elapsed timer."""

    def __init__(self, controller: object) -> None:
        self._controller = controller

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center gap-4"):
                # Start Meeting button — visible in IDLE only
                self._start_btn = ui.button(
                    "Start Meeting",
                    on_click=self._on_start,
                    icon="fiber_manual_record",
                ).classes("bg-green-600 text-white")

                # Stop Meeting button — visible in ACTIVE only
                self._stop_btn = ui.button(
                    "Stop Meeting",
                    on_click=self._on_stop,
                    icon="stop",
                ).classes("bg-red-600 text-white")
                self._stop_btn.set_visibility(False)

                # New Meeting button — visible in POST-MEETING only
                self._new_btn = ui.button(
                    "New Meeting",
                    on_click=self._on_new,
                )
                self._new_btn.set_visibility(False)

                # Recording indicator + timer row
                with ui.row().classes("items-center gap-2") as self._timer_row:
                    self._indicator = ui.icon("fiber_manual_record").classes(
                        "text-red-500 animate-pulse"
                    )
                    self._timer_label = ui.label("00:00:00").classes(
                        "text-xl font-mono font-bold"
                    )
                self._timer_row.set_visibility(False)

    async def _on_start(self) -> None:
        await self._controller.start_meeting()  # type: ignore[attr-defined]

    async def _on_stop(self) -> None:
        await self._controller.stop_meeting()  # type: ignore[attr-defined]

    async def _on_new(self) -> None:
        await self._controller.reset_to_idle()  # type: ignore[attr-defined]

    def set_state(self, state: str) -> None:
        """Update button visibility and timer based on meeting state."""
        is_idle = state == "idle"
        is_active = state == "active"
        is_post = state == "post_meeting"

        self._start_btn.set_visibility(is_idle)
        self._stop_btn.set_visibility(is_active)
        self._new_btn.set_visibility(is_post)
        self._timer_row.set_visibility(is_active or is_post)

        # Pulsing indicator only during active meeting
        if is_active:
            self._indicator.classes(add="animate-pulse")
        else:
            self._indicator.classes(remove="animate-pulse")

    def update_timer(self, elapsed_seconds: int) -> None:
        """Called every second by AppController timer tick."""
        h = elapsed_seconds // 3600
        m = (elapsed_seconds % 3600) // 60
        s = elapsed_seconds % 60
        self._timer_label.set_text(f"{h:02d}:{m:02d}:{s:02d}")
