"""Prompt registry for the two-lane card copilot.

The 21-button estate is gone. What remains:
- 5 reactive card prompts (answer_this, fact_check, reframe, where_are_we,
  next_step) — card output via forced emit_cards tool use, max_tokens 400.
- ask — freeform question, card output, max_tokens 600 (not a button; exposed
  as ``ASK_PROMPT_CONFIG``).
- 3 post-meeting long-form prompts kept as-is (meeting_summary, action_items,
  key_decisions) plus the background MEETING_TITLE_PROMPT template.
- Custom user prompts (AppConfig.custom_prompts) still work — they run as
  reactive-style card prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from storage.app_config import AppConfig

import config

from .templates import (
    ACTION_ITEMS_PROMPT,
    ANSWER_THIS_INSTRUCTION,
    ASK_QUESTION_PROMPT,
    FACT_CHECK_INSTRUCTION,
    KEY_DECISIONS_PROMPT,
    MEETING_SUMMARY_PROMPT,
    NEXT_STEP_INSTRUCTION,
    REFRAME_INSTRUCTION,
    WHERE_ARE_WE_INSTRUCTION,
)


BucketType = Literal["reactive", "post_meeting", "custom"]


@dataclass
class PromptConfig:
    id: str  # Unique identifier
    button_text: str  # Text for the button in the action bar
    template: str  # Reactive: the per-request instruction. Post-meeting: {transcript} template.
    output_title: str  # Title displayed in the output panel
    template_type: str  # Stream-handler key (post-meeting) or "card" (reactive)
    bucket: BucketType = field(default="reactive")
    model: str = config.REACTIVE_MODEL
    max_tokens: int = config.REACTIVE_MAX_TOKENS


PROMPT_REGISTRY = [
    # --- Reactive lane: exactly 5 buttons ---
    PromptConfig(
        id="answer_this",
        button_text="Answer this",
        template=ANSWER_THIS_INSTRUCTION,
        output_title="Answer",
        template_type="card",
        bucket="reactive",
    ),
    PromptConfig(
        id="fact_check",
        button_text="Fact-check",
        template=FACT_CHECK_INSTRUCTION,
        output_title="Fact Check",
        template_type="card",
        bucket="reactive",
    ),
    PromptConfig(
        id="reframe",
        button_text="Reframe",
        template=REFRAME_INSTRUCTION,
        output_title="Reframe",
        template_type="card",
        bucket="reactive",
    ),
    PromptConfig(
        id="where_are_we",
        button_text="Where are we?",
        template=WHERE_ARE_WE_INSTRUCTION,
        output_title="Where We Are",
        template_type="card",
        bucket="reactive",
    ),
    PromptConfig(
        id="next_step",
        button_text="Next step",
        template=NEXT_STEP_INSTRUCTION,
        output_title="Suggested Next Step",
        template_type="card",
        bucket="reactive",
    ),
    # --- Post-meeting lane: long-form streaming, kept as today ---
    PromptConfig(
        id="meeting_summary",
        button_text="Meeting Summary",
        template=MEETING_SUMMARY_PROMPT,
        output_title="Meeting Summary",
        template_type="meeting-summary",
        bucket="post_meeting",
        model=config.POST_MEETING_MODEL,
        max_tokens=config.POST_MEETING_MAX_TOKENS,
    ),
    PromptConfig(
        id="action_items",
        button_text="Action Items",
        template=ACTION_ITEMS_PROMPT,
        output_title="Action Items",
        template_type="action-items",
        bucket="post_meeting",
        model=config.POST_MEETING_MODEL,
        max_tokens=config.POST_MEETING_MAX_TOKENS,
    ),
    PromptConfig(
        id="key_decisions",
        button_text="Key Decisions",
        template=KEY_DECISIONS_PROMPT,
        output_title="Key Decisions",
        template_type="key-decisions",
        bucket="post_meeting",
        model=config.POST_MEETING_MODEL,
        max_tokens=config.POST_MEETING_MAX_TOKENS,
    ),
]


# Freeform Ask box — not a registry button, but the same reactive card path.
ASK_PROMPT_CONFIG = PromptConfig(
    id="ask",
    button_text="Ask",
    template=ASK_QUESTION_PROMPT,
    output_title="Answer",
    template_type="card",
    bucket="reactive",
    model=config.REACTIVE_MODEL,
    max_tokens=config.ASK_MAX_TOKENS,
)


def get_prompt_config_by_id(prompt_id: str) -> PromptConfig | None:
    if prompt_id == ASK_PROMPT_CONFIG.id:
        return ASK_PROMPT_CONFIG
    for cfg in PROMPT_REGISTRY:
        if cfg.id == prompt_id:
            return cfg
    return None


def get_effective_registry(app_config: AppConfig) -> list[PromptConfig]:
    """Return the full prompt list: built-ins with overrides applied + custom prompts appended.

    Custom prompts run as reactive-style card prompts (their template text is
    the per-request instruction).
    """
    result: list[PromptConfig] = []
    for cfg in PROMPT_REGISTRY:
        if cfg.id in app_config.deleted_prompt_ids:
            continue
        overrides = app_config.prompt_overrides.get(cfg.id, {})
        if overrides:
            cfg = replace(cfg, **{k: v for k, v in overrides.items() if hasattr(cfg, k)})
        result.append(cfg)

    for cp in app_config.custom_prompts:
        result.append(
            PromptConfig(
                id=cp.id,
                button_text=cp.button_text,
                template=cp.template,
                output_title=cp.output_title,
                template_type="card",
                bucket="custom",
                model=config.REACTIVE_MODEL,
                max_tokens=config.ASK_MAX_TOKENS,
            )
        )
    return result


def get_prompts_by_bucket(bucket: BucketType) -> list[PromptConfig]:
    """Return all built-in prompts for a given bucket ("reactive" | "post_meeting")."""
    return [cfg for cfg in PROMPT_REGISTRY if cfg.bucket == bucket]
