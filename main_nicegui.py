"""NiceGUI entry point for Darin Audio Assistant (DAR2-26).

Separate from the existing PyQt6 main.py (HoE decision: keep both
during transition, retire main.py when PyQt6 UI is fully removed).

Usage:
    uv run python main_nicegui.py
"""

from __future__ import annotations

from nicegui import ui

import config
from app_controller import AppController
from storage.meeting_store import MeetingStore
from ui.pages.meeting_page import create_meeting_page


def main() -> None:
    """Initialize AppController and start NiceGUI server."""
    # Validate API keys
    config.validate_api_keys()

    # Initialize backend
    controller = AppController()
    controller.meeting_store = MeetingStore()

    # Start continuous recording (circular buffer always running)
    controller.start_recording()

    # Register NiceGUI pages
    create_meeting_page(controller)

    # Start NiceGUI server on localhost
    ui.run(
        title="Darin Audio Assistant",
        host="127.0.0.1",
        port=0,  # Random ephemeral port
        show=True,  # Open browser automatically
        reload=False,
    )


if __name__ == "__main__":
    main()
