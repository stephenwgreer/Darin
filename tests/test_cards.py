"""Tests for the card schema — validation, defensive truncation, defaults."""

from __future__ import annotations

from services.cards import (
    CARD_TYPES,
    EMIT_CARDS_TOOL,
    MAX_BULLET_CHARS,
    MAX_BULLETS,
    MAX_HEADLINE_CHARS,
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
            "bullets",
            "say_this",
            "confidence",
            "urgency",
            "source",
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
