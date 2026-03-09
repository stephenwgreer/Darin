"""Tests for AppController post-construction callback wiring (DAR2-36).

Verifies that `on_stream_chunk`, `on_processing_complete`, and `on_progress`
can be assigned as properties after construction and that the private fields
read by `_run_prompt_thread` are updated accordingly.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest

from app_controller import AppController


@pytest.fixture
def controller() -> AppController:
    """Return an AppController with all backend dependencies mocked out."""
    with (
        patch("app_controller.ContinuousRecorder"),
        patch("app_controller.ApiClient"),
    ):
        yield AppController()


class TestCallbackSettersExist:
    """Verify the property setters are present on AppController."""

    def test_on_stream_chunk_property_exists(self, controller: AppController) -> None:
        prop = type(controller).__dict__.get("on_stream_chunk")
        assert prop is not None, "on_stream_chunk should be a property"
        assert isinstance(prop, property)

    def test_on_processing_complete_property_exists(self, controller: AppController) -> None:
        prop = type(controller).__dict__.get("on_processing_complete")
        assert prop is not None, "on_processing_complete should be a property"
        assert isinstance(prop, property)

    def test_on_progress_property_exists(self, controller: AppController) -> None:
        prop = type(controller).__dict__.get("on_progress")
        assert prop is not None, "on_progress should be a property"
        assert isinstance(prop, property)


class TestCallbacksNoneByDefault:
    """All callback properties default to None when no args given to __init__."""

    def test_on_stream_chunk_is_none_by_default(self, controller: AppController) -> None:
        assert controller.on_stream_chunk is None

    def test_on_processing_complete_is_none_by_default(self, controller: AppController) -> None:
        assert controller.on_processing_complete is None

    def test_on_progress_is_none_by_default(self, controller: AppController) -> None:
        assert controller.on_progress is None


class TestConstructorWiringUnchanged:
    """Constructor-time callback wiring (PyQt6 path) must still work."""

    def test_constructor_on_stream_chunk_is_readable(self) -> None:
        callback: Callable[[str], None] = MagicMock()
        with (
            patch("app_controller.ContinuousRecorder"),
            patch("app_controller.ApiClient"),
        ):
            ctrl = AppController(on_stream_chunk=callback)

        assert ctrl.on_stream_chunk is callback
        assert ctrl._on_stream_chunk is callback

    def test_constructor_on_processing_complete_is_readable(self) -> None:
        callback: Callable[[dict], None] = MagicMock()
        with (
            patch("app_controller.ContinuousRecorder"),
            patch("app_controller.ApiClient"),
        ):
            ctrl = AppController(on_processing_complete=callback)

        assert ctrl.on_processing_complete is callback
        assert ctrl._on_processing_complete is callback

    def test_constructor_on_progress_is_readable(self) -> None:
        callback: Callable[[str], None] = MagicMock()
        with (
            patch("app_controller.ContinuousRecorder"),
            patch("app_controller.ApiClient"),
        ):
            ctrl = AppController(on_progress=callback)

        assert ctrl.on_progress is callback
        assert ctrl._on_progress is callback


class TestPostConstructionCallbackSetting:
    """Callbacks assigned after construction must update private fields.

    This is the core regression check for DAR2-36: OutputPanel assigns
    callbacks after the controller is constructed, and _run_prompt_thread
    reads the private _on_stream_chunk / _on_processing_complete fields.
    """

    def test_setting_on_stream_chunk_updates_private_field(self, controller: AppController) -> None:
        callback: Callable[[str], None] = MagicMock()
        controller.on_stream_chunk = callback

        assert controller._on_stream_chunk is callback

    def test_setting_on_processing_complete_updates_private_field(
        self, controller: AppController
    ) -> None:
        callback: Callable[[dict], None] = MagicMock()
        controller.on_processing_complete = callback

        assert controller._on_processing_complete is callback

    def test_setting_on_progress_updates_private_field(self, controller: AppController) -> None:
        callback: Callable[[str], None] = MagicMock()
        controller.on_progress = callback

        assert controller._on_progress is callback

    def test_getter_returns_what_setter_stored(self, controller: AppController) -> None:
        callback: Callable[[str], None] = MagicMock()
        controller.on_stream_chunk = callback

        assert controller.on_stream_chunk is callback

    def test_callback_can_be_cleared_after_setting(self, controller: AppController) -> None:
        callback: Callable[[str], None] = MagicMock()
        controller.on_stream_chunk = callback
        controller.on_stream_chunk = None

        assert controller.on_stream_chunk is None
        assert controller._on_stream_chunk is None

    def test_callback_can_be_replaced(self, controller: AppController) -> None:
        first_callback: Callable[[str], None] = MagicMock()
        second_callback: Callable[[str], None] = MagicMock()

        controller.on_stream_chunk = first_callback
        controller.on_stream_chunk = second_callback

        assert controller._on_stream_chunk is second_callback

    def test_all_three_callbacks_set_independently(self, controller: AppController) -> None:
        stream_cb: Callable[[str], None] = MagicMock()
        complete_cb: Callable[[dict], None] = MagicMock()
        progress_cb: Callable[[str], None] = MagicMock()

        controller.on_stream_chunk = stream_cb
        controller.on_processing_complete = complete_cb
        controller.on_progress = progress_cb

        assert controller._on_stream_chunk is stream_cb
        assert controller._on_processing_complete is complete_cb
        assert controller._on_progress is progress_cb


class TestOutputPanelStyleAssignment:
    """Simulate how OutputPanel assigns callbacks (the DAR2-36 bug scenario)."""

    def test_nicegui_style_assignment_wires_private_field(self, controller: AppController) -> None:
        """Reproduce the exact OutputPanel assignment pattern.

        Before DAR2-36 this created a stray public attribute instead of
        updating _on_stream_chunk, so _run_prompt_thread never saw the
        callback.
        """
        received_chunks: list[str] = []

        # This is exactly how OutputPanel wires the controller
        controller.on_stream_chunk = lambda chunk: received_chunks.append(chunk)
        controller.on_processing_complete = lambda result: received_chunks.append(
            result.get("result", "")
        )

        # Simulate what _run_prompt_thread does
        assert controller._on_stream_chunk is not None
        controller._on_stream_chunk("Hello ")
        controller._on_stream_chunk("world")

        assert controller._on_processing_complete is not None
        controller._on_processing_complete({"result": "Hello world"})

        assert received_chunks == ["Hello ", "world", "Hello world"]

    def test_no_stray_public_attribute_created(self, controller: AppController) -> None:
        """Setting the property must NOT create a separate instance attribute.

        If a stray attribute were created, it would shadow the property on
        reads but _run_prompt_thread would still see the original None value
        in the private field.
        """
        callback: Callable[[str], None] = MagicMock()
        controller.on_stream_chunk = callback

        # The instance __dict__ must not contain 'on_stream_chunk'
        # (that would mean the descriptor was bypassed)
        assert "on_stream_chunk" not in controller.__dict__
