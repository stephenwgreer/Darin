"""API client for Anthropic and Deepgram services.

Provides the shared cache-first request shape for all three LLM lanes:

    system   = [stable instructions block, context-pack block]   (cached)
    messages = [append-only transcript blocks (cached breakpoint on last)]
             + [per-request instruction]                          (uncached)

Live-lane JSON cards are obtained by FORCED TOOL USE (``emit_cards``) — see
``services.cards``. Retries are SDK-only: the watcher lane uses a dedicated
client with ``max_retries=0, timeout=8s`` so a stalled tick can never queue
behind a live meeting; every other lane uses SDK defaults (max_retries=2).

Per-call usage telemetry (input/output/cache tokens + estimated $) is logged
via loguru and accumulated into a per-meeting cost readout.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
from anthropic import Anthropic
from loguru import logger

import config
from api.deepgram_utils import transcribe_with_deepgram
from api.providers import (
    ModelRegistry,
    ProviderSpec,
    create_cards_openai,
    extract_json_object,
    process_openai,
)
from services.cards import EMIT_CARDS_TOOL, Card, parse_cards


# Pricing per million tokens: model -> (input $, output $). Cache reads bill at
# ~0.1x input, cache writes at ~1.25x input (5-minute TTL).
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
}
_CACHE_READ_MULT = 0.1
_CACHE_WRITE_MULT = 1.25

# Default stable system instructions for lanes that don't supply their own
# (post-meeting analyses, titles, map-reduce, rolling summary).
DEFAULT_SYSTEM_INSTRUCTIONS = (
    "You are Darin, a meeting copilot. You analyze meeting transcripts where "
    'lines may be prefixed "ME:" (the user) and "THEM:" (other participants). '
    "Follow the task instruction at the end of the request exactly."
)


def estimate_cost_usd(model: str, usage: Any) -> float:
    """Estimate the $ cost of one call from its usage block."""
    pricing = _MODEL_PRICING.get(model)
    if pricing is None:
        # Fall back to the most expensive known tier so we never under-report.
        pricing = _MODEL_PRICING[config.POST_MEETING_MODEL]
    input_price, output_price = pricing
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (
        input_tokens * input_price
        + cache_read * input_price * _CACHE_READ_MULT
        + cache_write * input_price * _CACHE_WRITE_MULT
        + output_tokens * output_price
    ) / 1_000_000


def build_web_search_tool(model: str) -> dict:
    """Build the Anthropic server-side web-search tool for a given model (F3).

    The dynamic-filtering ``web_search_20260209`` variant requires an
    Opus-4.6+/Sonnet-4.6+ class model; Haiku falls back to the basic variant.
    """
    if model.startswith("claude-haiku"):
        tool_type = config.ANTHROPIC_WEB_SEARCH_TOOL_TYPE_BASIC
    else:
        tool_type = config.ANTHROPIC_WEB_SEARCH_TOOL_TYPE
    return {
        "type": tool_type,
        "name": "web_search",
        "max_uses": config.ANTHROPIC_WEB_SEARCH_MAX_USES,
    }


def build_system_blocks(instructions: str, context_pack_text: str | None = None) -> list[dict]:
    """Build the cached system prefix: [stable instructions, context pack].

    ``cache_control`` goes on the LAST system block so the whole prefix
    (tools + system) is cached together.
    """
    blocks: list[dict] = [{"type": "text", "text": instructions}]
    if context_pack_text and context_pack_text.strip():
        blocks.append({"type": "text", "text": context_pack_text})
    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    return blocks


def build_transcript_messages(
    transcript_blocks: list[str],
    instruction: str,
    *,
    cache_transcript: bool = True,
) -> list[dict]:
    """Build messages: append-only transcript blocks + final uncached instruction.

    The cache breakpoint sits on the LAST transcript block; because the block
    list only ever grows, each request re-reads the previous prefix and writes
    only the new tail (the watcher-lane incremental cache).
    """
    content: list[dict] = [
        {"type": "text", "text": block} for block in transcript_blocks if block and block.strip()
    ]
    messages: list[dict] = []
    if content:
        if cache_transcript:
            content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
        messages.append({"role": "user", "content": content})
    messages.append({"role": "user", "content": [{"type": "text", "text": instruction}]})
    return messages


class ApiClient:
    """Client for interacting with Anthropic and Deepgram APIs."""

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        deepgram_api_key: str | None = None,
        *,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        """
        Initialize API client with validated API keys.

        Args:
            anthropic_api_key: Optional override for Anthropic API key (uses config default)
            deepgram_api_key: Optional override for Deepgram API key (uses config default)
            model_registry: Optional model registry (F2). When set, model ids are
                resolved through it so openai_compat models route to the OpenAI-SDK
                adapter; unknown/anthropic ids stay on the native path. When None,
                every request uses the native Anthropic path (backwards compatible).

        Raises:
            ValueError: If API keys are invalid (empty or whitespace-only)
        """
        # Use provided keys or fall back to validated config module keys.
        # Use explicit None check so an empty string ("") bypasses the fallback
        # and reaches the validation block below, raising ValueError as expected.
        self.anthropic_api_key = (
            anthropic_api_key if anthropic_api_key is not None else config.ANTHROPIC_API_KEY
        )
        self.deepgram_api_key = (
            deepgram_api_key if deepgram_api_key is not None else config.DEEPGRAM_API_KEY
        )

        if not self.anthropic_api_key or not self.anthropic_api_key.strip():
            raise ValueError("Anthropic API key must be provided and non-empty")
        if not self.deepgram_api_key or not self.deepgram_api_key.strip():
            raise ValueError("Deepgram API key must be provided and non-empty")

        self._anthropic_client: Anthropic | None = None
        self._watcher_anthropic_client: Anthropic | None = None

        # F2: resolves model ids to providers. Settable after construction so the
        # controller can rebind it when custom endpoints change.
        self.model_registry: ModelRegistry | None = model_registry

        # Per-meeting cost telemetry
        self._cost_lock = threading.Lock()
        self._meeting_cost_usd: float = 0.0
        # Invoked after every call with {"meeting_cost_usd": float} — the
        # controller wires this to the SSE "usage" event.
        self.on_usage: Callable[[dict], None] | None = None

    # ------------------------------------------------------------------
    # Lane-specific Anthropic clients
    # ------------------------------------------------------------------

    @property
    def anthropic_client(self) -> Anthropic:
        """Lazy-load the default Anthropic client (SDK defaults: max_retries=2)."""
        if self._anthropic_client is None:
            self._anthropic_client = Anthropic(api_key=self.anthropic_api_key)
        return self._anthropic_client

    @property
    def watcher_anthropic_client(self) -> Anthropic:
        """Watcher-lane client: fail fast (max_retries=0, timeout=8s)."""
        if self._watcher_anthropic_client is None:
            self._watcher_anthropic_client = Anthropic(
                api_key=self.anthropic_api_key,
                max_retries=config.WATCHER_MAX_RETRIES,
                timeout=config.WATCHER_TIMEOUT_S,
            )
        return self._watcher_anthropic_client

    # ------------------------------------------------------------------
    # Usage / cost telemetry
    # ------------------------------------------------------------------

    @property
    def meeting_cost_usd(self) -> float:
        with self._cost_lock:
            return self._meeting_cost_usd

    def reset_meeting_cost(self) -> None:
        with self._cost_lock:
            self._meeting_cost_usd = 0.0

    def _record_usage(self, *, lane: str, model: str, response: Any) -> None:
        """Log per-call usage + cost, accumulate meeting cost, flag truncation."""
        usage = getattr(response, "usage", None)
        stop_reason = getattr(response, "stop_reason", None)
        cost = estimate_cost_usd(model, usage) if usage is not None else 0.0
        with self._cost_lock:
            self._meeting_cost_usd += cost
            total = self._meeting_cost_usd

        logger.info(
            "LLM call usage",
            lane=lane,
            model=model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None),
            cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None),
            stop_reason=stop_reason,
            call_cost_usd=f"{cost:.6f}",
            meeting_cost_usd=f"{total:.4f}",
        )
        if stop_reason == "max_tokens":
            logger.warning("LLM response truncated at max_tokens", lane=lane, model=model)
        if self.on_usage is not None:
            try:
                self.on_usage({"meeting_cost_usd": round(total, 6)})
            except Exception as e:  # noqa: BLE001 — telemetry must never break a lane
                logger.warning("on_usage callback failed: {}", e)

    # ------------------------------------------------------------------
    # Provider routing (F2)
    # ------------------------------------------------------------------

    def _resolve_provider(self, model: str) -> ProviderSpec | None:
        """Resolve a model id via the registry, or None (→ native Anthropic path)."""
        if self.model_registry is None:
            return None
        return self.model_registry.resolve(model)

    # ------------------------------------------------------------------
    # Card lanes (forced tool use)
    # ------------------------------------------------------------------

    def create_cards(
        self,
        *,
        lane: str,
        model: str,
        max_tokens: int,
        system: list[dict],
        messages: list[dict],
        web_search: bool = False,
    ) -> list[Card]:
        """Run one card request and return validated Cards.

        Anthropic models go through forced ``emit_cards`` tool use (or, when
        ``web_search`` is set, an unforced tools list so the model can search
        first). openai_compat models route to the OpenAI-SDK adapter.

        Args:
            lane: "watcher" (fail-fast client, proactive cards) or "reactive".
            model: Model ID for this lane.
            max_tokens: Per-prompt output cap.
            system: Cached system blocks (see ``build_system_blocks``).
            messages: Transcript context + final instruction
                (see ``build_transcript_messages``).
            web_search: Attach the Anthropic server-side web-search tool (F3);
                ignored (with a warning) on openai_compat models.

        Returns:
            Zero or more validated Cards (``[]`` is the "nothing to say" result).
        """
        card_lane = "proactive" if lane == "watcher" else "reactive"

        spec = self._resolve_provider(model)
        if spec is not None and spec.provider == "openai_compat":
            if web_search:
                logger.warning("web_search requested on openai_compat model — ignored", model=model)
            return create_cards_openai(
                spec,
                lane=lane,
                card_lane=card_lane,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )

        client = self.watcher_anthropic_client if lane == "watcher" else self.anthropic_client

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if web_search:
            # Unforced tools list: the model searches, then emits cards LAST.
            # Forcing emit_cards would prevent it from ever calling web_search.
            kwargs["tools"] = [EMIT_CARDS_TOOL, build_web_search_tool(model)]
        else:
            kwargs["tools"] = [EMIT_CARDS_TOOL]
            kwargs["tool_choice"] = {"type": "tool", "name": "emit_cards"}
            if lane == "reactive":
                # REACTIVE_MODEL defaults to adaptive thinking when the param is
                # omitted — the reactive lane explicitly disables it for latency.
                # With web search we leave thinking adaptive so the server-tool
                # loop can reason between searches.
                kwargs["thinking"] = {"type": "disabled"}

        response = client.messages.create(**kwargs)
        self._record_usage(lane=lane, model=model, response=response)

        # Server-tool (web search) loop: resume until the turn completes.
        continuations = 0
        while getattr(response, "stop_reason", None) == "pause_turn" and continuations < 3:
            continuations += 1
            resumed_messages = [*messages, {"role": "assistant", "content": response.content}]
            response = client.messages.create(**{**kwargs, "messages": resumed_messages})
            self._record_usage(lane=lane, model=model, response=response)

        # Take the LAST emit_cards tool_use block (it comes after any search).
        raw_input: object = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == (
                "emit_cards"
            ):
                raw_input = block.input

        if raw_input is None and web_search:
            # Fallback: the model may have answered in text instead of the tool.
            text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            raw_input = extract_json_object(text)

        if raw_input is None:
            logger.warning("No emit_cards tool_use block in response", lane=lane)
            return []

        cards = parse_cards(raw_input, lane=card_lane)
        if web_search:
            # Cards produced with web search are grounded in general/searched
            # knowledge unless the model already tagged them KB-grounded.
            for card in cards:
                if card.source != "kb":
                    card.source = "knowledge"
        return cards

    # ------------------------------------------------------------------
    # Long-form lane (post-meeting / titles / map-reduce / rolling summary)
    # ------------------------------------------------------------------

    @staticmethod
    def _split_template(prompt_template: str | None) -> str:
        """Extract the instruction text from a legacy ``{transcript}`` template.

        Legacy templates embed the transcript mid-template; the cache-first
        shape sends the transcript as a cached block and the instruction as the
        FINAL uncached message, so we lift the instruction text out. Uses
        ``partition`` (not ``format``) so stray braces never raise.

        When a placeholder was lifted out, a pointer to the transcript's real
        location is appended so the instruction never ends in a dangling
        content label (e.g. "Transcript:") that points at nothing.
        """
        if not prompt_template:
            return "Respond to the transcript above."
        if "{transcript}" in prompt_template:
            pre, _, post = prompt_template.partition("{transcript}")
            instruction = "\n\n".join(part.strip() for part in (pre, post) if part.strip())
            if not instruction:
                return "Respond to the transcript above."
            return instruction + "\n\n(The transcript is provided in the previous message.)"
        return prompt_template.strip()

    def process_with_anthropic(
        self,
        text: str,
        prompt_template: str | None = None,
        stream: bool = True,
        callback: Callable[[str], None] | None = None,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        system_instructions: str | None = None,
        context_pack_text: str | None = None,
        lane: str = "background",
        cache_transcript: bool = True,
        web_search: bool = False,
    ) -> str:
        """Process a transcript with Claude using the cache-first request shape.

        Args:
            text: The transcript text (sent as a cached block).
            prompt_template: Legacy template with a ``{transcript}`` placeholder;
                its instruction text is sent as the final uncached message.
            stream: Whether to stream the response.
            callback: Optional callback for streaming chunks.
            model: Model ID (default: POST_MEETING_MODEL).
            max_tokens: Output cap (default: POST_MEETING_MAX_TOKENS).
            system_instructions: Stable system block text (default generic).
            context_pack_text: Optional context pack appended to the cached system.
            lane: Telemetry label ("background" | "interactive").
            cache_transcript: Whether to put a cache breakpoint on the transcript
                block. Pass False for one-shot lanes (map-reduce chunks, titles,
                rolling summary) where the block is never re-read — a cache
                write there is a pure 1.25x input premium.

        Returns:
            Complete response text from Claude.

        Raises:
            ValueError: If the Anthropic API key is not set.
            anthropic.APIError subclasses: On API failure (SDK-managed retries only).
        """
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not set")

        model = model or config.POST_MEETING_MODEL
        max_tokens = max_tokens or config.POST_MEETING_MAX_TOKENS
        instruction = self._split_template(prompt_template)
        system = build_system_blocks(
            system_instructions or DEFAULT_SYSTEM_INSTRUCTIONS, context_pack_text
        )
        transcript_block = f"<transcript>\n{text}\n</transcript>" if text else ""
        messages = build_transcript_messages(
            [transcript_block], instruction, cache_transcript=cache_transcript
        )

        # F2: route openai_compat models through the OpenAI-SDK adapter.
        spec = self._resolve_provider(model)
        if spec is not None and spec.provider == "openai_compat":
            if web_search:
                logger.warning("web_search requested on openai_compat model — ignored", model=model)
            logger.info(
                "Sending prompt to openai_compat model",
                lane=lane,
                model=model,
                transcript_chars=len(text),
            )
            return process_openai(
                spec,
                lane=lane,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                stream=stream,
                callback=callback,
            )

        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if web_search:
            request_kwargs["tools"] = [build_web_search_tool(model)]
        # claude-sonnet-5 runs ADAPTIVE thinking when the param is omitted:
        # thinking tokens bill as output and count against max_tokens, so the
        # long-form/background lanes disable it explicitly. With web search we
        # leave thinking adaptive so the server-tool loop can reason. claude-
        # haiku-4-5 runs WITHOUT thinking when the param is omitted.
        if model.startswith("claude-sonnet-5") and not web_search:
            request_kwargs["thinking"] = {"type": "disabled"}

        client = self.anthropic_client
        logger.info(
            "Sending prompt to Claude API",
            lane=lane,
            model=model,
            transcript_chars=len(text),
        )

        if stream:
            response_chunks: list[str] = []
            with client.messages.stream(**request_kwargs) as stream_context:
                for chunk_text in stream_context.text_stream:
                    response_chunks.append(chunk_text)
                    if callback:
                        callback(chunk_text)
                final_message = stream_context.get_final_message()

            self._record_usage(lane=lane, model=model, response=final_message)
            response_text = "".join(response_chunks)
            logger.info(f"Completed streaming response: {len(response_text)} chars")
            return response_text

        response = client.messages.create(**request_kwargs)
        self._record_usage(lane=lane, model=model, response=response)
        response_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        logger.info(f"Received complete response: {len(response_text)} chars")
        return response_text

    # ------------------------------------------------------------------
    # Deepgram batch path
    # ------------------------------------------------------------------

    def transcribe_with_deepgram(self, audio_data: np.ndarray, sample_rate: int) -> str:
        """
        Transcribe audio using Deepgram API (batch/REST path).

        Args:
            audio_data: Audio samples as a numpy array (mono int16 expected)
            sample_rate: Sample rate of the audio in Hz

        Returns:
            Transcribed text

        Raises:
            ValueError: If Deepgram API key is not set or audio data is invalid
            RuntimeError: If transcription fails
        """
        if not self.deepgram_api_key:
            raise ValueError("Deepgram API key not set")

        if audio_data is None or len(audio_data) == 0:
            raise ValueError("Audio data cannot be empty")

        logger.info(f"Transcribing audio: {len(audio_data)} samples at {sample_rate} Hz")

        try:
            result = transcribe_with_deepgram(self.deepgram_api_key, audio_data, sample_rate)
            logger.info(f"Transcription complete: {len(result)} characters")
            return result
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription error: {e}") from e
