"""Data-driven stream handler registry for routing streamed HTML items to UI lists.

Replaces 15 duplicated elif blocks in main_window.on_stream_update() with a single
parameterized handler. Each template type is defined by a config entry that specifies
how to extract items and where to route them.

Sprint 2 Item #8 — deduplicate stream parsing.
"""

from __future__ import annotations

import re

# Default inline styles applied to single-list items
_STYLE_BOLD = (
    'display: list-item !important; list-style-type: disc !important; '
    'font-weight: bold !important;'
)
_STYLE_NORMAL = (
    'display: list-item !important; list-style-type: disc !important;'
)

# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------
# Three handler types:
#   "single-list"    — all items go to one target list, with optional styling
#   "multi-list"     — items routed by CSS class → list ID mapping
#   "class-derived"  — list ID derived from the item's CSS class name + suffix
#
# Every entry must have:
#   pattern  — regex for _extract_html_items()
#
# single-list also has:
#   target   — the list element ID (e.g. "dynamic-content")
#   style    — "bold" | "normal" (controls inline style injection)
#
# multi-list also has:
#   class_to_list — dict mapping CSS class substring → list element ID
#                   Uses simple substring matching (not regex)
#   group_classes — optional dict mapping list ID → list of class substrings
#                   that all route to the same list (for grouped classes)
#
# class-derived also has:
#   list_suffix — appended to class name to form list ID

TEMPLATE_REGISTRY: dict[str, dict] = {
    # --- Single-list templates (items → #dynamic-content) ---
    "follow-up-questions": {
        "type": "single-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "target": "dynamic-content",
        "style": "bold",
    },
    "meeting-summary": {
        "type": "single-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "target": "dynamic-content",
        "style": "normal",
    },
    "topic-summary": {
        "type": "single-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "target": "dynamic-content",
        "style": "normal",
    },
    "practitioner-insights": {
        "type": "single-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "target": "dynamic-content",
        "style": "normal",
    },
    # --- Multi-list templates (items routed by CSS class) ---
    "fill-gaps": {
        "type": "multi-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "class_to_list": {
            "core-thinking": "core-thinking-list",
            "gap-item": "gaps-list",
            "recommendation-item": "recommendations-list",
        },
    },
    "brainstorm": {
        "type": "multi-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "class_to_list": {
            "challenge-question": "challenge-questions-list",
            "alternative-frame": "alternative-frames-list",
            "provocative-idea": "provocative-ideas-list",
        },
    },
    "company-fit": {
        "type": "multi-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "class_to_list": {
            "key-topic": "key-topics-list",
            "viya-connection": "viya-connections-list",
            "missing-consideration": "missing-considerations-list",
        },
    },
    "fact-check": {
        "type": "multi-list",
        "pattern": r'<li class=["\']fact-check-item["\']>.*?</li>',
        "class_to_list": {
            "fact-check-item": "fact-check-list",
        },
    },
    "answer-question": {
        "type": "multi-list",
        "pattern": r'<li class=["\'](?:answer-item|rationale-item|example-item)["\']>.*?</li>',
        "class_to_list": {
            "answer-item": "answer-list",
            "rationale-item": "rationale-list",
            "example-item": "examples-list",
        },
    },
    "problem-solving": {
        "type": "multi-list",
        "pattern": (
            r'<li class=["\'](?:core-problem|logic-tree-component|'
            r'evaluation-(?:mece|assumption|logic|data)|'
            r'challenge-(?:weakness|question|reframe))["\']>.*?</li>'
        ),
        "class_to_list": {
            "core-problem": "core-problem-list",
            "logic-tree-component": "logic-tree-list",
        },
        "group_classes": {
            "evaluation-list": [
                "evaluation-mece",
                "evaluation-assumption",
                "evaluation-logic",
                "evaluation-data",
            ],
            "challenge-list": [
                "challenge-weakness",
                "challenge-question",
                "challenge-reframe",
            ],
        },
    },
    "hypothesis-driven": {
        "type": "multi-list",
        "pattern": (
            r'<li class=["\']hypothesis-(?:problem|hypothesis|'
            r'evidence-(?:support|contradict|missing)|'
            r'priority|testing|decision|assessment)["\']>.*?</li>'
        ),
        "class_to_list": {
            "hypothesis-problem": "hypothesis-problem-list",
            "hypothesis-hypothesis": "hypothesis-hypothesis-list",
            "hypothesis-priority": "hypothesis-priority-list",
            "hypothesis-testing": "hypothesis-testing-list",
            "hypothesis-decision": "hypothesis-decision-list",
            "hypothesis-assessment": "hypothesis-assessment-list",
        },
        "group_classes": {
            "hypothesis-evidence-list": [
                "hypothesis-evidence-support",
                "hypothesis-evidence-contradict",
                "hypothesis-evidence-missing",
            ],
        },
    },
    # --- Class-derived templates (list ID = class name + suffix) ---
    "scqa": {
        "type": "class-derived",
        "pattern": (
            r'<li class=["\']scqa-(?:situation|complication|question|'
            r'answer|assessment|roadmap)["\']>.*?</li>'
        ),
        "list_suffix": "-list",
    },
    "first-principles": {
        "type": "class-derived",
        "pattern": (
            r'<li class=["\']fp-(?:conventional|fundamental|assumption|'
            r'rebuild|insight|implementation|metacognitive)["\']>.*?</li>'
        ),
        "list_suffix": "-list",
    },
    "reframing": {
        "type": "class-derived",
        "pattern": r'<li class=["\']reframing-(?:statement|point)["\']>.*?</li>',
        "list_suffix": "-list",
    },
}


def _apply_single_list_style(item: str, style: str) -> str:
    """Apply inline styling to a single-list item (matching original behavior)."""
    inline = _STYLE_BOLD if style == "bold" else _STYLE_NORMAL
    if "class=" not in item:
        return item.replace(
            "<li",
            f'<li class="insight-item" style="{inline}"',
        )
    elif 'style="' not in item:
        return item.replace(
            'class="',
            f'class="insight-item" style="{inline}"',
        )
    return item


def route_stream_item(
    item: str, config: dict
) -> tuple[str, str] | None:
    """Route a single extracted HTML item to its target list.

    Returns (list_id, processed_item_html) or None if no match.
    """
    handler_type = config["type"]

    if handler_type == "single-list":
        styled = _apply_single_list_style(item, config.get("style", "normal"))
        return (config["target"], styled)

    elif handler_type == "multi-list":
        # Check direct class_to_list mappings
        class_to_list = config.get("class_to_list", {})
        for css_class, list_id in class_to_list.items():
            if css_class in item:
                return (list_id, item)

        # Check grouped classes
        group_classes = config.get("group_classes", {})
        for list_id, class_list in group_classes.items():
            if any(cls in item for cls in class_list):
                return (list_id, item)

        return None

    elif handler_type == "class-derived":
        class_match = re.search(r'class=["\']([^"\']+)["\']', item)
        if class_match:
            list_id = class_match.group(1) + config.get("list_suffix", "-list")
            return (list_id, item)
        return None

    return None
