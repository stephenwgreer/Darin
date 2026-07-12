"""Card schema — single source of truth for both LLM lanes and the frontend.

A card is the atomic unit the copilot renders:

    {
      id: str, lane: "proactive"|"reactive",
      type: "answer"|"fact_check"|"reframe"|"status"|"next_step"|"question"|
            "deep_dive"|"heads_up",
      trigger: str|null, headline: str (<=60 chars),
      bullets: [str] (<=3, each <=140 chars),
      cues: [str] (<=3, each <=3 words) — instant-glance keywords,
      say_this: str|null,
      confidence: "high"|"medium", urgency: "now"|"soon"|"fyi",
      source: "transcript"|"kb"|"knowledge", expires_in_s: int, topic_key: str
    }

Cards are obtained by FORCED TOOL USE: every card-producing request passes
``EMIT_CARDS_TOOL`` with ``tool_choice={"type": "tool", "name": "emit_cards"}``
so the model must return ``{"cards": [...]}`` (``{"cards": []}`` is the valid
"nothing to say" response). ``parse_cards`` is deliberately defensive — the
model output is clamped to the schema rather than rejected.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field

from loguru import logger


CARD_LANES = ("proactive", "reactive")
CARD_TYPES = (
    "answer",
    "fact_check",
    "reframe",
    "status",
    "next_step",
    "question",
    "deep_dive",
    "heads_up",
)
CARD_CONFIDENCES = ("high", "medium")
CARD_URGENCIES = ("now", "soon", "fyi")
CARD_SOURCES = ("transcript", "kb", "knowledge")

MAX_HEADLINE_CHARS = 60
MAX_BULLETS = 3
MAX_BULLET_CHARS = 140
# F4: cues are instant-glance keywords — at most 3, each at most 3 words.
MAX_CUES = 3
MAX_CUE_WORDS = 3

_DEFAULT_EXPIRES_S = {"proactive": 45, "reactive": 300}


@dataclass
class Card:
    """A single glanceable copilot card."""

    id: str
    lane: str  # "proactive" | "reactive"
    type: str  # one of CARD_TYPES
    trigger: str | None
    headline: str
    bullets: list[str] = field(default_factory=list)
    # F4: instant-glance keywords (<=3, each <=3 words) — what the user reads
    # mid-sentence when bullets are too slow.
    cues: list[str] = field(default_factory=list)
    say_this: str | None = None
    confidence: str = "medium"
    urgency: str = "fyi"
    source: str = "transcript"
    expires_in_s: int = 45
    topic_key: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# Forced-tool-use definition. One tool, one required "cards" array — robust
# across SDK versions (no structured-outputs / strict-mode dependency).
EMIT_CARDS_TOOL: dict = {
    "name": "emit_cards",
    "description": (
        "Emit zero or more copilot cards for the user. "
        'Return {"cards": []} when there is nothing worth saying.'
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": list(CARD_TYPES)},
                        "trigger": {"type": ["string", "null"]},
                        "headline": {
                            "type": "string",
                            "description": "Glanceable headline, max 60 characters.",
                        },
                        "bullets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Up to 3 bullets, each max 140 characters.",
                        },
                        "cues": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Up to 3 instant-glance keyword cues, each max 3 words "
                                '(e.g. "not k8s-compatible", "suggest OpenShift", '
                                '"ask pricing") — what the user reads mid-sentence when '
                                "bullets are too slow."
                            ),
                        },
                        "say_this": {
                            "type": ["string", "null"],
                            "description": (
                                "One sentence the user could say out loud verbatim, or null."
                            ),
                        },
                        "confidence": {"type": "string", "enum": list(CARD_CONFIDENCES)},
                        "urgency": {"type": "string", "enum": list(CARD_URGENCIES)},
                        "source": {"type": "string", "enum": list(CARD_SOURCES)},
                        "expires_in_s": {"type": "integer"},
                        "topic_key": {
                            "type": "string",
                            "description": "Short kebab-case topic slug for deduplication.",
                        },
                    },
                    "required": ["type", "headline"],
                },
            }
        },
        "required": ["cards"],
    },
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "card"


def _clamp_str(value: object, max_chars: int) -> str:
    text = str(value).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def _pick(value: object, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def parse_card(raw: object, *, lane: str) -> Card | None:
    """Parse one raw card dict defensively; return None only if unusable."""
    if not isinstance(raw, dict):
        return None

    headline = _clamp_str(raw.get("headline") or "", MAX_HEADLINE_CHARS)
    if not headline:
        return None

    lane = lane if lane in CARD_LANES else "reactive"
    card_type = _pick(raw.get("type"), CARD_TYPES, "heads_up")

    bullets_raw = raw.get("bullets")
    bullets: list[str] = []
    if isinstance(bullets_raw, list):
        for item in bullets_raw[:MAX_BULLETS]:
            text = _clamp_str(item, MAX_BULLET_CHARS)
            if text:
                bullets.append(text)

    cues_raw = raw.get("cues")
    cues: list[str] = []
    if isinstance(cues_raw, list):
        for item in cues_raw[:MAX_CUES]:
            cue = " ".join(str(item).split()[:MAX_CUE_WORDS]).strip()
            if cue:
                cues.append(cue)

    say_this_raw = raw.get("say_this")
    say_this = str(say_this_raw).strip() or None if say_this_raw is not None else None

    trigger_raw = raw.get("trigger")
    trigger = str(trigger_raw).strip() or None if trigger_raw is not None else None

    expires_raw = raw.get("expires_in_s")
    try:
        expires_in_s = int(expires_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        expires_in_s = _DEFAULT_EXPIRES_S[lane]
    expires_in_s = max(5, min(expires_in_s, 3600))

    topic_key_raw = raw.get("topic_key")
    topic_key = (
        _slugify(str(topic_key_raw))
        if isinstance(topic_key_raw, str) and topic_key_raw.strip()
        else _slugify(headline)
    )

    return Card(
        id=f"card_{uuid.uuid4().hex[:12]}",
        lane=lane,
        type=card_type,
        trigger=trigger,
        headline=headline,
        bullets=bullets,
        cues=cues,
        say_this=say_this,
        confidence=_pick(raw.get("confidence"), CARD_CONFIDENCES, "medium"),
        urgency=_pick(raw.get("urgency"), CARD_URGENCIES, "fyi"),
        source=_pick(raw.get("source"), CARD_SOURCES, "transcript"),
        expires_in_s=expires_in_s,
        topic_key=topic_key,
    )


def parse_cards(raw_input: object, *, lane: str) -> list[Card]:
    """Parse an emit_cards tool input ({"cards": [...]}) into validated Cards.

    Malformed entries are dropped with a warning rather than failing the call —
    cards=[] is a perfectly valid "nothing to say" result.
    """
    if not isinstance(raw_input, dict):
        logger.warning("emit_cards input was not a dict", input_type=type(raw_input).__name__)
        return []
    cards_raw = raw_input.get("cards")
    if not isinstance(cards_raw, list):
        logger.warning("emit_cards input missing 'cards' list")
        return []

    cards: list[Card] = []
    for entry in cards_raw:
        card = parse_card(entry, lane=lane)
        if card is not None:
            cards.append(card)
        else:
            logger.warning("Dropped unparseable card entry", entry=str(entry)[:200])
    return cards
