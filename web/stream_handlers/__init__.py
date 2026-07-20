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

# Only the KEPT post-meeting long-form prompts stream through this registry.
# Live lanes (watcher + reactive) emit atomic card events and bypass the
# StreamBuffer entirely.
TEMPLATE_REGISTRY: dict[str, dict] = {
    "meeting-summary": {
        "type": "single-list",
        "pattern": r"<li[^>]*>.*?</li>",
        "target": "dynamic-content",
        "style": "normal",
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


def _apply_single_list_style(item: str, style: str) -> str:
    """Apply inline styling to a single-list item (matching original behavior)."""
    if style == "default":
        return item
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
    "meeting-summary": _SINGLE_LIST_SCAFFOLD,
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
