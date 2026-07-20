"""Model registry + OpenAI-compatible provider adapter (F2).

The registry produces the model list the frontend renders in the per-prompt
model dropdown and, crucially, tells :mod:`api.client` how to route a request:

    [{id, label, provider: "anthropic"|"openai_compat",
      model_name, available: bool, supports_web_search: bool}, ...]

Two kinds of models exist:

- **Anthropic built-ins** — ``claude-sonnet-5`` and ``claude-haiku-4-5``. Always
  available (the Anthropic key exists), and the only models that support the
  server-side web-search tool (F3).
- **User-defined OpenAI-compatible endpoints** — from ``AppConfig.custom_endpoints``
  (Groq / Gemini-OpenAI-compat / Cerebras / local Ollama / a ChatJimmy-style
  proxy). The code knows nothing provider-specific: it is just ``base_url`` +
  ``/chat/completions`` via the ``openai`` SDK. Web search is never supported.

Card generation on an openai_compat model first tries tool/function-calling with
the ``emit_cards`` function; on ANY failure it falls back to JSON-mode prompting
and the existing defensive parse in :mod:`services.cards`. Long-form generation
uses a standard streaming chat completion. No prompt-caching semantics are
assumed. The watcher lane fails fast (8 s timeout, no retries); every other lane
uses the SDK defaults.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger
from openai import OpenAI

import config
from services.cards import EMIT_CARDS_TOOL, Card, parse_cards


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from storage.app_config import AppConfig, CustomEndpointConfig


# Anthropic built-ins: (model id, display label). Always available because an
# Anthropic key is required to run the app at all.
_ANTHROPIC_BUILTINS: tuple[tuple[str, str], ...] = (
    ("claude-sonnet-5", "Claude Sonnet 5"),
    ("claude-haiku-4-5", "Claude Haiku 4.5"),
)

# JSON-mode fallback instruction appended when function-calling is unavailable.
_JSON_MODE_INSTRUCTION = (
    "Respond ONLY with a JSON object matching this schema and nothing else "
    '(no prose, no markdown fences): {"cards": [ ... ]}. Each card object has '
    "keys: type, trigger, headline, key_fact, bullets (array of strings), say_this, "
    "confidence, urgency (now|fyi), source, disposition, update, expires_in_s, "
    'topic_key. Return {"cards": []} when there is nothing worth saying.'
)


@dataclass
class ProviderSpec:
    """A resolved model: everything a lane needs to route one request."""

    id: str
    label: str
    provider: str  # "anthropic" | "openai_compat"
    model_name: str
    available: bool = True
    supports_web_search: bool = False
    base_url: str | None = None
    api_key: str = ""


class ModelRegistry:
    """Resolve model ids to provider specs and enumerate the public model list."""

    def __init__(
        self,
        app_config: AppConfig | None = None,
        *,
        custom_endpoints: Iterable[CustomEndpointConfig] | None = None,
    ) -> None:
        if custom_endpoints is not None:
            endpoints = list(custom_endpoints)
        elif app_config is not None:
            endpoints = list(app_config.custom_endpoints)
        else:
            endpoints = []
        # Last write wins on duplicate ids (defensive — the API enforces unique).
        self._custom: dict[str, CustomEndpointConfig] = {e.id: e for e in endpoints}

    def list(self) -> list[dict[str, Any]]:
        """Return the public model list for GET /api/models (no api_keys)."""
        out: list[dict[str, Any]] = []
        for mid, label in _ANTHROPIC_BUILTINS:
            out.append(
                {
                    "id": mid,
                    "label": label,
                    "provider": "anthropic",
                    "model_name": mid,
                    "available": True,
                    "supports_web_search": True,
                }
            )
        for e in self._custom.values():
            out.append(
                {
                    "id": e.id,
                    "label": e.label,
                    "provider": "openai_compat",
                    "model_name": e.model_name,
                    "available": bool(e.base_url),
                    "supports_web_search": False,
                }
            )
        return out

    def resolve(self, model_id: str) -> ProviderSpec | None:
        """Resolve a model id to a ProviderSpec, or None if unknown.

        An unknown id resolves to None so the caller can safely fall back to the
        native Anthropic path (backwards compatible with hard-coded model ids).
        """
        for mid, label in _ANTHROPIC_BUILTINS:
            if model_id == mid:
                return ProviderSpec(
                    id=mid,
                    label=label,
                    provider="anthropic",
                    model_name=mid,
                    available=True,
                    supports_web_search=True,
                )
        e = self._custom.get(model_id)
        if e is not None:
            return ProviderSpec(
                id=e.id,
                label=e.label,
                provider="openai_compat",
                model_name=e.model_name,
                available=bool(e.base_url),
                supports_web_search=False,
                base_url=e.base_url,
                api_key=e.api_key,
            )
        return None


# ---------------------------------------------------------------------------
# Anthropic-block → OpenAI-message flattening
# ---------------------------------------------------------------------------


def _flatten_content(content: object) -> str:
    """Flatten an Anthropic content value (str | list[block]) into plain text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n\n".join(parts)


def flatten_system(system: list[dict]) -> str:
    """Join cached Anthropic system blocks into one system string."""
    return _flatten_content(system)


def to_openai_messages(system: list[dict], messages: list[dict]) -> list[dict[str, str]]:
    """Convert Anthropic (system, messages) into OpenAI chat messages."""
    out: list[dict[str, str]] = [{"role": "system", "content": flatten_system(system)}]
    for m in messages:
        role = m.get("role", "user")
        out.append({"role": role, "content": _flatten_content(m.get("content"))})
    return out


def extract_json_object(text: str) -> dict | None:
    """Best-effort extract the first JSON object from a text blob.

    Tolerates markdown fences and surrounding prose — used for the JSON-mode
    fallback and for text-fallback parsing when a web-search card prompt does
    not emit the tool call.
    """
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(stripped[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------------
# OpenAI-compatible client + generation
# ---------------------------------------------------------------------------


def _build_client(spec: ProviderSpec, lane: str) -> OpenAI:
    """Build an OpenAI-compat client. Watcher lane fails fast; others default."""
    kwargs: dict[str, Any] = {
        "base_url": spec.base_url,
        "api_key": spec.api_key or "dummy",
    }
    if lane == "watcher":
        kwargs["timeout"] = config.OPENAI_COMPAT_WATCHER_TIMEOUT_S
        kwargs["max_retries"] = config.OPENAI_COMPAT_WATCHER_MAX_RETRIES
    return OpenAI(**kwargs)


def _emit_cards_function() -> dict:
    """Build the OpenAI function-tool form of the emit_cards tool."""
    return {
        "type": "function",
        "function": {
            "name": EMIT_CARDS_TOOL["name"],
            "description": EMIT_CARDS_TOOL["description"],
            "parameters": EMIT_CARDS_TOOL["input_schema"],
        },
    }


def _tool_call_arguments(response: Any) -> dict | None:
    """Extract emit_cards arguments from an OpenAI tool-call response."""
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError):
        return None
    tool_calls = getattr(message, "tool_calls", None) or []
    for call in tool_calls:
        fn = getattr(call, "function", None)
        if fn is not None and getattr(fn, "name", None) == "emit_cards":
            args = getattr(fn, "arguments", None)
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                except (ValueError, TypeError):
                    return None
                return parsed if isinstance(parsed, dict) else None
            if isinstance(args, dict):
                return args
    return None


def create_cards_openai(
    spec: ProviderSpec,
    *,
    lane: str,
    card_lane: str,
    max_tokens: int,
    system: list[dict],
    messages: list[dict],
) -> list[Card]:
    """Generate cards on an openai_compat endpoint.

    Tries function-calling with the emit_cards function; on ANY failure falls
    back to JSON-mode prompting + the defensive parse in ``services.cards``.
    """
    client = _build_client(spec, lane)
    oai_messages = to_openai_messages(system, messages)

    try:
        response = client.chat.completions.create(
            model=spec.model_name,
            messages=oai_messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            tools=[_emit_cards_function()],  # type: ignore[list-item]
            tool_choice={"type": "function", "function": {"name": "emit_cards"}},
        )
        raw = _tool_call_arguments(response)
        if raw is not None:
            return parse_cards(raw, lane=card_lane)
        logger.warning(
            "openai_compat emit_cards tool call absent — falling back to JSON mode",
            model=spec.id,
        )
    except Exception as e:  # noqa: BLE001 — any SDK/proxy failure → JSON fallback
        logger.warning(
            "openai_compat function-calling failed; falling back to JSON mode: {}",
            e,
            model=spec.id,
        )

    fallback_messages = to_openai_messages(system, messages)
    fallback_messages.append({"role": "user", "content": _JSON_MODE_INSTRUCTION})
    response = client.chat.completions.create(
        model=spec.model_name,
        messages=fallback_messages,  # type: ignore[arg-type]
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content or ""
    raw = extract_json_object(text)
    if raw is None:
        logger.warning(
            "openai_compat JSON-mode fallback produced no parseable cards", model=spec.id
        )
        return []
    return parse_cards(raw, lane=card_lane)


def process_openai(
    spec: ProviderSpec,
    *,
    lane: str,
    max_tokens: int,
    system: list[dict],
    messages: list[dict],
    stream: bool = True,
    callback: Callable[[str], None] | None = None,
) -> str:
    """Run a long-form completion on an openai_compat endpoint (streams by default)."""
    client = _build_client(spec, lane)
    oai_messages = to_openai_messages(system, messages)

    if stream:
        chunks: list[str] = []
        response = client.chat.completions.create(
            model=spec.model_name,
            messages=oai_messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0].delta, "content", None)
            if delta:
                chunks.append(delta)
                if callback is not None:
                    callback(delta)
        return "".join(chunks)

    response = client.chat.completions.create(
        model=spec.model_name,
        messages=oai_messages,  # type: ignore[arg-type]
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
