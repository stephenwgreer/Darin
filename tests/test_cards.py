"""Tests for the card schema — validation, defensive truncation, defaults."""

from __future__ import annotations

from services.cards import (
    CARD_TYPES,
    EMIT_CARDS_TOOL,
    MAX_BULLET_CHARS,
    MAX_BULLETS,
    MAX_CUE_WORDS,
    MAX_CUES,
    MAX_HEADLINE_CHARS,
    MAX_KEY_FACT_CHARS,
    MAX_WATCHER_BULLET_CHARS,
    parse_card,
    parse_cards,
)


class TestEmitCardsTool:
    def test_tool_shape(self) -> None:
        assert EMIT_CARDS_TOOL["name"] == "emit_cards"
        schema = EMIT_CARDS_TOOL["input_schema"]
        assert schema["required"] == ["cards"]
        assert schema["properties"]["cards"]["type"] == "array"

    def test_card_types_in_schema_match_module(self) -> None:
        item_props = EMIT_CARDS_TOOL["input_schema"]["properties"]["cards"]["items"]["properties"]
        assert item_props["type"]["enum"] == list(CARD_TYPES)

    def test_cues_in_schema(self) -> None:
        item_props = EMIT_CARDS_TOOL["input_schema"]["properties"]["cards"]["items"]["properties"]
        assert item_props["cues"]["type"] == "array"


class TestParseCard:
    def test_valid_card_round_trip(self) -> None:
        card = parse_card(
            {
                "type": "answer",
                "trigger": "question_at_user",
                "headline": "Redis licensing",
                "bullets": ["Point one", "Point two"],
                "say_this": "We already handle that.",
                "confidence": "high",
                "urgency": "now",
                "source": "kb",
                "expires_in_s": 60,
                "topic_key": "redis-licensing",
            },
            lane="proactive",
        )
        assert card is not None
        assert card.lane == "proactive"
        assert card.type == "answer"
        assert card.trigger == "question_at_user"
        assert card.headline == "Redis licensing"
        assert card.bullets == ["Point one", "Point two"]
        assert card.say_this == "We already handle that."
        assert card.confidence == "high"
        assert card.urgency == "now"
        assert card.source == "kb"
        assert card.expires_in_s == 60
        assert card.topic_key == "redis-licensing"
        assert card.id.startswith("card_")

    def test_headline_truncated_to_60(self) -> None:
        card = parse_card({"type": "answer", "headline": "x" * 200}, lane="reactive")
        assert card is not None
        assert len(card.headline) <= MAX_HEADLINE_CHARS

    def test_bullets_truncated_to_3_and_140_chars(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "bullets": ["y" * 300] * 6},
            lane="reactive",
        )
        assert card is not None
        assert len(card.bullets) == MAX_BULLETS
        assert all(len(b) <= MAX_BULLET_CHARS for b in card.bullets)

    def test_proactive_lane_clamps_bullets_to_80(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "bullets": ["y" * 300]},
            lane="proactive",
        )
        assert card is not None
        assert all(len(b) <= MAX_WATCHER_BULLET_CHARS for b in card.bullets)

    def test_reactive_lane_clamps_bullets_to_140(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "bullets": ["y" * 300]},
            lane="reactive",
        )
        assert card is not None
        assert all(len(b) <= MAX_BULLET_CHARS for b in card.bullets)

    def test_cues_parsed(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "cues": ["ask pricing", "suggest OpenShift"]},
            lane="reactive",
        )
        assert card is not None
        assert card.cues == ["ask pricing", "suggest OpenShift"]

    def test_cues_truncated_to_3_and_3_words(self) -> None:
        card = parse_card(
            {
                "type": "answer",
                "headline": "h",
                "cues": ["one two three four five", "a", "b", "c", "d"],
            },
            lane="reactive",
        )
        assert card is not None
        assert len(card.cues) == MAX_CUES
        assert card.cues[0] == "one two three"
        assert all(len(c.split()) <= MAX_CUE_WORDS for c in card.cues)

    def test_cues_default_empty_and_bad_type_ignored(self) -> None:
        card = parse_card({"type": "answer", "headline": "h"}, lane="reactive")
        assert card is not None
        assert card.cues == []
        card2 = parse_card(
            {"type": "answer", "headline": "h", "cues": "not a list"}, lane="reactive"
        )
        assert card2 is not None
        assert card2.cues == []

    def test_invalid_enums_fall_back_to_defaults(self) -> None:
        card = parse_card(
            {
                "type": "essay",  # not a card type
                "headline": "h",
                "confidence": "certain",
                "urgency": "immediately",
                "source": "the internet",
            },
            lane="reactive",
        )
        assert card is not None
        assert card.type == "heads_up"
        assert card.confidence == "medium"
        assert card.urgency == "fyi"
        assert card.source == "transcript"

    def test_key_fact_parsed_and_clamped(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "key_fact": "x" * 100},
            lane="reactive",
        )
        assert card is not None
        assert len(card.key_fact) <= MAX_KEY_FACT_CHARS

        card2 = parse_card({"type": "answer", "headline": "h"}, lane="reactive")
        assert card2 is not None
        assert card2.key_fact is None

        card3 = parse_card(
            {"type": "answer", "headline": "h", "key_fact": "   "}, lane="reactive"
        )
        assert card3 is not None
        assert card3.key_fact is None

    def test_urgency_soon_migrates_to_now(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "urgency": "soon"}, lane="reactive"
        )
        assert card is not None
        assert card.urgency == "now"

    def test_urgency_unknown_falls_back_to_fyi(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "urgency": "whenever"}, lane="reactive"
        )
        assert card is not None
        assert card.urgency == "fyi"

    def test_disposition_and_update_parsed(self) -> None:
        card = parse_card(
            {
                "type": "answer",
                "headline": "h",
                "disposition": "log",
                "update": True,
            },
            lane="reactive",
        )
        assert card is not None
        assert card.disposition == "log"
        assert card.update is True

    def test_disposition_and_update_default(self) -> None:
        card = parse_card({"type": "answer", "headline": "h"}, lane="reactive")
        assert card is not None
        assert card.disposition == "render"
        assert card.update is False

    def test_disposition_invalid_falls_back_to_render(self) -> None:
        card = parse_card(
            {"type": "answer", "headline": "h", "disposition": "explode"},
            lane="reactive",
        )
        assert card is not None
        assert card.disposition == "render"

    def test_medium_confidence_say_this_nulled_and_bullet_hedged(self) -> None:
        card = parse_card(
            {
                "type": "answer",
                "headline": "h",
                "say_this": "We already handle that.",
                "bullets": ["Redis is included in the base license."],
                "confidence": "medium",
                "source": "kb",
            },
            lane="reactive",
        )
        assert card is not None
        assert card.say_this is None
        assert card.bullets[0] == "Likely: Redis is included in the base license."

    def test_medium_confidence_say_this_nulled_no_bullets_is_safe(self) -> None:
        card = parse_card(
            {
                "type": "answer",
                "headline": "h",
                "say_this": "We already handle that.",
                "confidence": "medium",
                "source": "kb",
            },
            lane="reactive",
        )
        assert card is not None
        assert card.say_this is None
        assert card.bullets == []

    def test_high_confidence_kb_source_keeps_say_this(self) -> None:
        card = parse_card(
            {
                "type": "answer",
                "headline": "h",
                "say_this": "We already handle that.",
                "bullets": ["Redis is included."],
                "confidence": "high",
                "source": "kb",
            },
            lane="reactive",
        )
        assert card is not None
        assert card.say_this == "We already handle that."
        assert card.bullets[0] == "Redis is included."

    def test_high_confidence_non_gating_source_keeps_say_this_unchanged(self) -> None:
        # Per the gate contract: only confidence != "high" triggers the
        # null-and-hedge path, so high-confidence say_this survives even
        # when the source isn't one of SAY_THIS_SOURCES.
        card = parse_card(
            {
                "type": "answer",
                "headline": "h",
                "say_this": "We already handle that.",
                "bullets": ["Redis is included."],
                "confidence": "high",
                "source": "knowledge",
            },
            lane="reactive",
        )
        assert card is not None
        assert card.say_this == "We already handle that."
        assert card.bullets[0] == "Redis is included."

    def test_topic_key_derived_from_headline_when_missing(self) -> None:
        card = parse_card({"type": "status", "headline": "Where We Are Now"}, lane="reactive")
        assert card is not None
        assert card.topic_key == "where-we-are-now"

    def test_expires_in_s_defaults_and_clamps(self) -> None:
        proactive = parse_card({"type": "answer", "headline": "h"}, lane="proactive")
        reactive = parse_card({"type": "answer", "headline": "h"}, lane="reactive")
        assert proactive is not None and proactive.expires_in_s == 45
        assert reactive is not None and reactive.expires_in_s == 300

        huge = parse_card(
            {"type": "answer", "headline": "h", "expires_in_s": 999_999}, lane="reactive"
        )
        assert huge is not None and huge.expires_in_s == 3600

    def test_missing_headline_rejects_card(self) -> None:
        assert parse_card({"type": "answer"}, lane="reactive") is None
        assert parse_card({"type": "answer", "headline": "   "}, lane="reactive") is None

    def test_non_dict_rejects_card(self) -> None:
        assert parse_card("not a dict", lane="reactive") is None

    def test_to_dict_has_full_schema(self) -> None:
        card = parse_card({"type": "answer", "headline": "h"}, lane="reactive")
        assert card is not None
        d = card.to_dict()
        for key in (
            "id",
            "lane",
            "type",
            "trigger",
            "headline",
            "key_fact",
            "bullets",
            "cues",
            "say_this",
            "confidence",
            "urgency",
            "source",
            "disposition",
            "update",
            "expires_in_s",
            "topic_key",
        ):
            assert key in d


class TestParseCards:
    def test_empty_cards_is_valid(self) -> None:
        assert parse_cards({"cards": []}, lane="proactive") == []

    def test_bad_input_types_return_empty(self) -> None:
        assert parse_cards(None, lane="proactive") == []
        assert parse_cards("garbage", lane="proactive") == []
        assert parse_cards({"cards": "not a list"}, lane="proactive") == []
        assert parse_cards({}, lane="proactive") == []

    def test_malformed_entries_dropped_valid_kept(self) -> None:
        cards = parse_cards(
            {
                "cards": [
                    {"type": "answer", "headline": "good"},
                    {"type": "answer"},  # no headline — dropped
                    "garbage",  # not a dict — dropped
                ]
            },
            lane="reactive",
        )
        assert len(cards) == 1
        assert cards[0].headline == "good"
