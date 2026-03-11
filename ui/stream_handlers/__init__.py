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
    "display: list-item !important; list-style-type: disc !important; font-weight: bold !important;"
)
_STYLE_NORMAL = "display: list-item !important; list-style-type: disc !important;"

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
#
# Optional on any entry:
#   first_line_parser — extract a value from the first line of stream text
#     valid_values    — list of accepted string values
#     callback_method — output_panel method name to call with the value

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
    "sentiment-analysis": {
        "type": "single-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "target": "dynamic-content",
        "style": "normal",
        "first_line_parser": {
            "valid_values": ["Positive", "Negative", "Neutral"],
            "callback_method": "set_overall_sentiment",
        },
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
            r"evaluation-(?:mece|assumption|logic|data)|"
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
            r"evidence-(?:support|contradict|missing)|"
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
    # --- New post-meeting + analyze-statement templates (DAR2-27) ---
    "analyze-statement": {
        "type": "multi-list",
        "pattern": r'<li class=["\']statement-(?:claim|strength|weakness|assumption|unsaid)["\']>.*?</li>',
        "class_to_list": {
            "statement-claim": "statement-claim-list",
            "statement-strength": "statement-strength-list",
            "statement-weakness": "statement-weakness-list",
            "statement-assumption": "statement-assumption-list",
            "statement-unsaid": "statement-unsaid-list",
        },
    },
    "action-items": {
        "type": "single-list",
        "pattern": r'<li class=["\']action-item["\']>.*?</li>',
        "target": "action-list",
        "style": "normal",
    },
    "key-decisions": {
        "type": "multi-list",
        "pattern": r'<li class=["\']decision-(?:made|needed)["\']>.*?</li>',
        "class_to_list": {
            "decision-made": "decision-made-list",
            "decision-needed": "decision-needed-list",
        },
    },
}


def parse_first_line_value(text: str, config: dict) -> tuple[str | None, str]:
    """Extract a first-line value from stream text if the config has a first_line_parser.

    Some templates (e.g. sentiment-analysis) expect the first line of the stream
    to contain a standalone value (e.g. "Positive") before the HTML list items begin.
    This function checks for that value and returns it along with the remaining text.

    Returns:
        (value, remaining_text) — value is None if no match or no parser configured.
    """
    flp = config.get("first_line_parser")
    if not flp:
        return None, text
    lines = text.split("\n", 1)
    value = lines[0].strip()
    if value in flp["valid_values"]:
        remaining = lines[1] if len(lines) > 1 else ""
        return value, remaining
    return None, text


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


def route_stream_item(item: str, config: dict) -> tuple[str, str] | None:
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


# ---------------------------------------------------------------------------
# Static scaffold templates (DAR2-37)
# ---------------------------------------------------------------------------
# Data-driven replacement for MainWindow._setup_static_template().
# Keyed by template_type (same keys as TEMPLATE_REGISTRY).
# Each value is the HTML scaffold that gets set before streaming begins.
# The scaffold contains empty <ul> containers with IDs that match
# the routing targets in TEMPLATE_REGISTRY.

_SINGLE_LIST_SCAFFOLD = """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <ul class="insight-list" id="dynamic-content" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
"""

STATIC_TEMPLATES: dict[str, str] = {
    # --- Single-list templates (all share the same scaffold) ---
    "follow-up-questions": _SINGLE_LIST_SCAFFOLD,
    "meeting-summary": _SINGLE_LIST_SCAFFOLD,
    "topic-summary": _SINGLE_LIST_SCAFFOLD,
    "practitioner-insights": _SINGLE_LIST_SCAFFOLD,
    "sentiment-analysis": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">Overall Sentiment</h3>
    <p id="overall-sentiment-value" style="margin-left: 10px;"></p>
    <h3 style="font-weight: bold; margin-top: 20px;">Key Emotional Moments</h3>
    <ul class="insight-list" id="dynamic-content" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    # --- Multi-list templates ---
    "fill-gaps": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">CORE THINKING</h3>
    <ul id="core-thinking-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">GAPS</h3>
    <ul id="gaps-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">RECOMMENDATIONS</h3>
    <ul id="recommendations-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "brainstorm": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">CHALLENGE QUESTIONS</h3>
    <ul id="challenge-questions-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">ALTERNATIVE FRAMES</h3>
    <ul id="alternative-frames-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">PROVOCATIVE IDEAS</h3>
    <ul id="provocative-ideas-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "company-fit": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">KEY TOPICS</h3>
    <ul id="key-topics-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">SAS VIYA CONNECTIONS</h3>
    <ul id="viya-connections-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">MISSING CONSIDERATIONS</h3>
    <ul id="missing-considerations-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "fact-check": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">Fact Check Analysis</h3>
    <ul id="fact-check-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
</div>
""",
    "answer-question": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">ANSWER</h3>
    <ul id="answer-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">RATIONALE</h3>
    <ul id="rationale-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">EXAMPLES</h3>
    <ul id="examples-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "problem-solving": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">CORE PROBLEM/OBJECTIVE</h3>
    <ul id="core-problem-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">LOGIC TREE COMPONENTS</h3>
    <ul id="logic-tree-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">EVALUATION</h3>
    <ul id="evaluation-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">CHALLENGE & REFRAME</h3>
    <ul id="challenge-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "hypothesis-driven": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">PROBLEM STATEMENT</h3>
    <ul id="hypothesis-problem-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">HYPOTHESES</h3>
    <ul id="hypothesis-hypothesis-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">EVIDENCE ANALYSIS</h3>
    <ul id="hypothesis-evidence-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">HYPOTHESIS PRIORITIZATION</h3>
    <ul id="hypothesis-priority-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">TESTING PLAN</h3>
    <ul id="hypothesis-testing-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">DECISION FRAMEWORK</h3>
    <ul id="hypothesis-decision-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">TRANSCRIPT ASSESSMENT</h3>
    <ul id="hypothesis-assessment-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    # --- Class-derived templates ---
    "scqa": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">SITUATION</h3>
    <ul id="scqa-situation-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">COMPLICATION</h3>
    <ul id="scqa-complication-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">QUESTION</h3>
    <ul id="scqa-question-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">ANSWER</h3>
    <ul id="scqa-answer-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">CRITICAL ASSESSMENT</h3>
    <ul id="scqa-assessment-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">IMPLEMENTATION ROADMAP</h3>
    <ul id="scqa-roadmap-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "first-principles": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">CONVENTIONAL THINKING</h3>
    <ul id="fp-conventional-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">FUNDAMENTALS</h3>
    <ul id="fp-fundamental-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">ASSUMPTION CHALLENGES</h3>
    <ul id="fp-assumption-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">REBUILD FROM FIRST PRINCIPLES</h3>
    <ul id="fp-rebuild-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">NOVEL INSIGHTS</h3>
    <ul id="fp-insight-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">IMPLEMENTATION FRAMEWORK</h3>
    <ul id="fp-implementation-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">METACOGNITIVE ASSESSMENT</h3>
    <ul id="fp-metacognitive-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "reframing": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">REFRAMED STATEMENT</h3>
    <ul id="reframing-statement-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">SUPPORTING POINTS</h3>
    <ul id="reframing-point-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "analyze-statement": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">CORE CLAIM</h3>
    <ul id="statement-claim-list" style="list-style-type: none; margin-top: 0; padding-left: 0;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">STRENGTHS</h3>
    <ul id="statement-strength-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">WEAKNESSES</h3>
    <ul id="statement-weakness-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">ASSUMPTIONS</h3>
    <ul id="statement-assumption-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">WHAT IS UNSAID</h3>
    <ul id="statement-unsaid-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "action-items": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <ul class="insight-list" id="action-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    "key-decisions": """
<div class="insight-block" style="margin-top: 0; padding-top: 10px;">
    <h3 style="font-weight: bold;">DECISIONS MADE</h3>
    <ul id="decision-made-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
    <h3 style="font-weight: bold; margin-top: 20px;">DECISIONS NEEDED</h3>
    <ul id="decision-needed-list" style="list-style-type: disc; margin-top: 0; padding-left: 25px;">
    </ul>
</div>
""",
    # --- Generic fallback ---
    "generic": """
<div class="topic-section">
    <h2 class="topic-title">Results</h2>
    <div class="insight-block" id="dynamic-content">
    </div>
</div>
""",
}
