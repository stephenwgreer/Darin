"""Reactive-lane RAG injection tests (Phase 3).

Drive ``AppController._run_reactive_thread`` synchronously with a fake
knowledge base and assert that retrieved SAS-doc chunks are injected into the
per-request transcript messages (never the cached system block), that no block
appears when retrieval returns nothing, and that a custom prompt with
``use_rag=False`` skips retrieval entirely.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app_controller import AppController
from prompts.registry import PromptConfig


_KB_BLOCK = (
    "Relevant SAS documentation (cite the source doc + page):\n"
    "[viya-admin.pdf p.42] Configure the CAS server via the SAS Environment Manager."
)


class _FakeKnowledgeBase:
    """Minimal stand-in matching the KnowledgeBase surface the reactive lane uses."""

    def __init__(self, hits: list[object], *, enabled: bool = True, is_empty: bool = False) -> None:
        self.enabled = enabled
        self._hits = hits
        self._is_empty = is_empty
        self.search = MagicMock(return_value=hits)

    @property
    def is_empty(self) -> bool:
        return self._is_empty

    def format_for_prompt(self, hits: list[object]) -> str:
        return _KB_BLOCK


@pytest.fixture
def controller() -> AppController:
    with (
        patch("app_controller.ContinuousRecorder"),
        patch("app_controller.ApiClient"),
    ):
        ctrl = AppController()
        # api_client is a MagicMock (patched ApiClient); make create_cards return
        # no cards and capture the system/messages it was called with.
        ctrl.api_client.create_cards = MagicMock(return_value=[])
        # A non-empty transcript override keeps us out of the no-transcript exit.
        yield ctrl


def _captured_call(ctrl: AppController) -> dict:
    ctrl.api_client.create_cards.assert_called_once()
    return ctrl.api_client.create_cards.call_args.kwargs


def _messages_text(kwargs: dict) -> str:
    # build_transcript_messages returns a list of message dicts; flatten their text.
    parts: list[str] = []
    for msg in kwargs["messages"]:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        else:
            for block in content:
                parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def _system_text(kwargs: dict) -> str:
    system = kwargs["system"]
    if isinstance(system, str):
        return system
    parts: list[str] = []
    for block in system:
        if isinstance(block, str):
            parts.append(block)
        else:
            parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def test_hits_injected_into_transcript_not_system(controller: AppController) -> None:
    hit = object()
    kb = _FakeKnowledgeBase([hit])
    controller.knowledge_base = kb
    prompt = PromptConfig(
        id="answer_this",
        button_text="Answer this",
        template="Answer the question.",
        output_title="Answer",
        template_type="card",
    )

    controller._run_reactive_thread(
        prompt,
        "How do I configure CAS?",
        "THEM: How do I configure CAS?",
        None,
    )

    kb.search.assert_called_once()
    kwargs = _captured_call(controller)
    # (a) the retrieved doc block (its citation text — distinct from the honesty
    # clause baked into the system prompt) lands in the per-request transcript
    # messages ...
    assert "[viya-admin.pdf p.42]" in _messages_text(kwargs)
    # ... and NOT in the cached system block (would bust the prompt cache).
    assert "[viya-admin.pdf p.42]" not in _system_text(kwargs)


def test_no_injection_when_no_hits(controller: AppController) -> None:
    kb = _FakeKnowledgeBase([])
    controller.knowledge_base = kb
    prompt = PromptConfig(
        id="answer_this",
        button_text="Answer this",
        template="Answer the question.",
        output_title="Answer",
        template_type="card",
    )

    controller._run_reactive_thread(
        prompt,
        "How do I configure CAS?",
        "THEM: How do I configure CAS?",
        None,
    )

    kb.search.assert_called_once()
    kwargs = _captured_call(controller)
    assert "[viya-admin.pdf p.42]" not in _messages_text(kwargs)


def test_use_rag_false_skips_search(controller: AppController) -> None:
    kb = _FakeKnowledgeBase([object()])
    controller.knowledge_base = kb
    prompt = PromptConfig(
        id="custom_x",
        button_text="Custom",
        template="Do the thing.",
        output_title="Custom",
        template_type="card",
        bucket="custom",
        use_rag=False,
    )

    controller._run_reactive_thread(
        prompt,
        "How do I configure CAS?",
        "THEM: How do I configure CAS?",
        None,
    )

    kb.search.assert_not_called()
    kwargs = _captured_call(controller)
    assert "[viya-admin.pdf p.42]" not in _messages_text(kwargs)
