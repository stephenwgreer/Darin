# DAR2-37: NiceGUI OutputPanel Streaming Bullet/Item Buffering

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Port the PyQt6 streaming display pipeline (buffer + extract + route + incremental DOM append) to the NiceGUI OutputPanel so Claude responses appear bullet-by-bullet as they stream.

**Architecture:** Create a `StreamBuffer` class that owns the `io.StringIO` buffer, lock, and extraction logic (currently embedded in `MainWindow`). The NiceGUI `OutputPanel` composes this buffer and uses `ui.run_javascript()` for incremental DOM appends. A new `STATIC_TEMPLATES` dict (data-driven, keyed by `template_type`) replaces the 300-line `_setup_static_template()` if/elif chain. `PromptButtons` passes `on_template_setup` to `controller.run_prompt()` so `template_type` is set before streaming begins.

**Tech Stack:** Python 3.11, NiceGUI, `io.StringIO`, `threading.Lock`, `re`, existing `TEMPLATE_REGISTRY` from `ui/stream_handlers.py`

---

## Task 1: Create `StreamBuffer` — Extract Buffer Logic into Reusable Class

**Files:**
- Create: `ui/stream_buffer.py`
- Test: `tests/test_stream_buffer.py`

This class extracts the buffering + regex extraction from `MainWindow._extract_html_items()` into a framework-agnostic, thread-safe class that both PyQt6 and NiceGUI can use.

**Step 1: Write the failing tests**

```python
# tests/test_stream_buffer.py
"""Tests for StreamBuffer (DAR2-37)."""

from __future__ import annotations

from ui.stream_buffer import StreamBuffer


class TestStreamBufferExtraction:
    """Test buffer accumulation and regex item extraction."""

    def test_complete_item_extracted(self) -> None:
        buf = StreamBuffer()
        items = buf.write_and_extract('<li class="x">hello</li>')
        assert items == ['<li class="x">hello</li>']

    def test_partial_item_buffered(self) -> None:
        buf = StreamBuffer()
        items = buf.write_and_extract('<li class="x">hel')
        assert items == []

    def test_partial_then_complete(self) -> None:
        buf = StreamBuffer()
        buf.write_and_extract('<li class="x">hel')
        items = buf.write_and_extract('lo</li>')
        assert items == ['<li class="x">hello</li>']

    def test_multiple_items_in_one_chunk(self) -> None:
        buf = StreamBuffer()
        items = buf.write_and_extract(
            '<li>one</li><li>two</li>'
        )
        assert items == ["<li>one</li>", "<li>two</li>"]

    def test_custom_pattern(self) -> None:
        buf = StreamBuffer(pattern=r'<li class="fact-check-item">.*?</li>')
        items = buf.write_and_extract(
            '<li class="fact-check-item">check</li><li class="other">skip</li>'
        )
        assert items == ['<li class="fact-check-item">check</li>']

    def test_remainder_preserved(self) -> None:
        buf = StreamBuffer()
        buf.write_and_extract('<li>done</li>leftover <li>par')
        items = buf.write_and_extract('tial</li>')
        assert items == ['<li>partial</li>']

    def test_clear_resets_buffer(self) -> None:
        buf = StreamBuffer()
        buf.write_and_extract("<li>partial")
        buf.clear()
        items = buf.write_and_extract("</li>")
        assert items == []  # old partial was cleared

    def test_multiline_item_extracted(self) -> None:
        buf = StreamBuffer()
        items = buf.write_and_extract('<li class="x">\nmultiline\n</li>')
        assert len(items) == 1
        assert "multiline" in items[0]


class TestStreamBufferThreadSafety:
    """Test that lock is used for buffer operations."""

    def test_lock_is_acquired(self) -> None:
        buf = StreamBuffer()
        # Verify the lock exists and is a threading.Lock
        import threading
        assert isinstance(buf._lock, type(threading.Lock()))
```

**Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_stream_buffer.py -v`
Expected: ModuleNotFoundError — `ui.stream_buffer` does not exist yet

**Step 3: Write minimal implementation**

```python
# ui/stream_buffer.py
"""Thread-safe streaming HTML buffer with regex item extraction (DAR2-37).

Extracted from MainWindow._extract_html_items() so both PyQt6 and NiceGUI
can share the same buffer + extraction logic without framework coupling.
"""

from __future__ import annotations

import io
import re
import threading

# Default pattern: any complete <li>...</li> tag (matches DOTALL for multiline)
_DEFAULT_PATTERN = r"<li[^>]*>.*?</li>"


class StreamBuffer:
    """Accumulates streaming text and extracts complete HTML items via regex.

    Thread-safe: all buffer operations are protected by an internal lock.
    Performance: uses io.StringIO for O(1) amortized append (not O(n^2) concat).
    """

    def __init__(self, pattern: str = _DEFAULT_PATTERN) -> None:
        self._pattern = pattern
        self._lock = threading.Lock()
        self._buffer = io.StringIO()

    def write_and_extract(self, text: str) -> list[str]:
        """Append text to buffer and return all complete items found.

        Incomplete items remain in the buffer for the next call.
        """
        with self._lock:
            self._buffer.seek(0, 2)
            self._buffer.write(text)
            content = self._buffer.getvalue()

            matches = list(re.finditer(self._pattern, content, re.DOTALL))
            if not matches:
                return []

            items = []
            removals = []
            for match in matches:
                items.append(match.group(0))
                removals.append((match.start(), match.end()))

            for start, end in reversed(removals):
                content = content[:start] + content[end:]

            self._buffer = io.StringIO(content)
            return items

    def clear(self) -> None:
        """Reset the buffer (call between prompts)."""
        with self._lock:
            self._buffer = io.StringIO()
```

**Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_stream_buffer.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
./scripts/wsl-git.sh add ui/stream_buffer.py tests/test_stream_buffer.py
./scripts/wsl-git.sh commit -m "feat(DAR2-37): add StreamBuffer for reusable HTML item extraction"
```

---

## Task 2: Create `STATIC_TEMPLATES` Data-Driven Registry

**Files:**
- Modify: `ui/stream_handlers.py` (add `STATIC_TEMPLATES` dict at the bottom)
- Test: `tests/test_static_templates.py`

This replaces the 300-line `_setup_static_template()` if/elif chain with a data-driven dict. Each entry maps a `template_type` string (from `PROMPT_REGISTRY`) to its scaffold HTML.

**Step 1: Write the failing tests**

```python
# tests/test_static_templates.py
"""Tests for STATIC_TEMPLATES registry (DAR2-37)."""

from __future__ import annotations

from ui.stream_handlers import STATIC_TEMPLATES, TEMPLATE_REGISTRY


class TestStaticTemplatesRegistry:
    """Verify every TEMPLATE_REGISTRY entry has a matching scaffold."""

    def test_all_registered_templates_have_scaffold(self) -> None:
        for template_type in TEMPLATE_REGISTRY:
            assert template_type in STATIC_TEMPLATES, (
                f"Missing STATIC_TEMPLATES entry for '{template_type}'"
            )

    def test_scaffold_contains_target_ids(self) -> None:
        """Each scaffold must contain the element IDs the router targets."""
        for template_type, config in TEMPLATE_REGISTRY.items():
            scaffold = STATIC_TEMPLATES[template_type]
            handler_type = config["type"]

            if handler_type == "single-list":
                target = config["target"]
                assert f'id="{target}"' in scaffold, (
                    f"{template_type}: missing id='{target}' in scaffold"
                )

            elif handler_type == "multi-list":
                for list_id in config.get("class_to_list", {}).values():
                    assert f'id="{list_id}"' in scaffold, (
                        f"{template_type}: missing id='{list_id}' in scaffold"
                    )
                for list_id in config.get("group_classes", {}).keys():
                    assert f'id="{list_id}"' in scaffold, (
                        f"{template_type}: missing id='{list_id}' in scaffold"
                    )

            elif handler_type == "class-derived":
                # class-derived IDs are built at runtime; just check scaffold exists
                assert len(scaffold.strip()) > 0

    def test_generic_fallback_exists(self) -> None:
        assert "generic" in STATIC_TEMPLATES
        assert 'id="dynamic-content"' in STATIC_TEMPLATES["generic"]
```

**Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_static_templates.py -v`
Expected: ImportError — `STATIC_TEMPLATES` not yet in `stream_handlers.py`

**Step 3: Add STATIC_TEMPLATES to stream_handlers.py**

Append this to the end of `ui/stream_handlers.py` (after `route_stream_item`):

```python
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
    # --- Generic fallback ---
    "generic": """
<div class="topic-section">
    <h2 class="topic-title">Results</h2>
    <div class="insight-block" id="dynamic-content">
    </div>
</div>
""",
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_static_templates.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
./scripts/wsl-git.sh add ui/stream_handlers.py tests/test_static_templates.py
./scripts/wsl-git.sh commit -m "feat(DAR2-37): add STATIC_TEMPLATES data-driven scaffold registry"
```

---

## Task 3: Rewrite NiceGUI `OutputPanel` with Streaming Buffer

**Files:**
- Modify: `ui/components/output_panel.py` (full rewrite)
- Test: `tests/test_output_panel.py` (full rewrite)

The OutputPanel gets: `StreamBuffer` composition, `TEMPLATE_REGISTRY` routing, `STATIC_TEMPLATES` scaffold setup, `ui.run_javascript()` incremental DOM appends, and thread-safe callback marshalling.

**Step 1: Write the failing tests**

```python
# tests/test_output_panel.py
"""Tests for NiceGUI OutputPanel streaming pipeline (DAR2-37)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call, patch


class TestOutputPanelSetup:
    """Test scaffold HTML installation before streaming begins."""

    def test_setup_template_sets_scaffold_html(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            panel.setup_template("fill-gaps")

            html_set = panel._content.set_content.call_args[0][0]
            assert 'id="core-thinking-list"' in html_set
            assert 'id="gaps-list"' in html_set

    def test_setup_template_clears_buffer(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            # Simulate leftover buffer state
            panel._buffer.write_and_extract("<li>partial")
            panel.setup_template("meeting-summary")

            # Buffer should be cleared — old partial should not appear
            items = panel._buffer.write_and_extract("</li>")
            assert items == []

    def test_setup_template_uses_config_pattern(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            panel.setup_template("fact-check")

            # fact-check has a specific pattern — verify buffer was recreated with it
            assert "fact-check-item" in panel._buffer._pattern


class TestOutputPanelStreaming:
    """Test chunk processing — buffer + extract + route."""

    def test_complete_item_appended_via_js(self) -> None:
        with patch("ui.components.output_panel.ui") as mock_ui:
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("meeting-summary")
            panel.handle_stream_chunk('<li class="insight-item">Point A</li>')

            # Should have called run_javascript for incremental append
            mock_ui.run_javascript.assert_called()
            js_call = mock_ui.run_javascript.call_args[0][0]
            assert "insertAdjacentHTML" in js_call
            assert "dynamic-content" in js_call

    def test_partial_item_not_appended(self) -> None:
        with patch("ui.components.output_panel.ui") as mock_ui:
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("meeting-summary")
            panel.handle_stream_chunk('<li class="insight-item">partial...')

            mock_ui.run_javascript.assert_not_called()

    def test_multi_list_routing(self) -> None:
        with patch("ui.components.output_panel.ui") as mock_ui:
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("fill-gaps")
            panel.handle_stream_chunk(
                '<li class="gap-item">Missing data</li>'
            )

            js_call = mock_ui.run_javascript.call_args[0][0]
            assert "gaps-list" in js_call


class TestOutputPanelFinalize:
    """Test _finalize behavior with registered templates."""

    def test_finalize_skips_replace_for_registered_template(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            panel.setup_template("fill-gaps")
            panel._finalize({"result": "raw text"})

            # Should NOT replace content — scaffold + streamed items are already correct
            panel._content.set_content.assert_not_called()

    def test_finalize_replaces_for_unregistered_template(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()
            panel._scroll = MagicMock()

            # No setup_template called — _template_type is None
            panel._finalize({"result": "Final analysis"})

            panel._content.set_content.assert_called_with("Final analysis")


class TestOutputPanelCallbackWiring:
    """Test controller callback registration."""

    def test_controller_callbacks_wired(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            OutputPanel(controller)

            assert controller.on_stream_chunk is not None
            assert controller.on_processing_complete is not None

    def test_clear_resets_state(self) -> None:
        with patch("ui.components.output_panel.ui"):
            from ui.components.output_panel import OutputPanel

            controller = MagicMock()
            panel = OutputPanel(controller)
            panel._content = MagicMock()

            panel.setup_template("fill-gaps")
            panel.clear()

            assert panel._template_type is None
            panel._content.set_content.assert_called_with("")
```

**Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_output_panel.py -v`
Expected: Multiple failures — `setup_template`, `handle_stream_chunk`, `_buffer` don't exist

**Step 3: Rewrite OutputPanel implementation**

```python
# ui/components/output_panel.py
"""Claude analysis results display with streaming buffer pipeline (DAR2-37).

Displays Claude analysis output with bullet-by-bullet streaming:
1. setup_template() installs scaffold HTML with empty <ul> containers
2. handle_stream_chunk() buffers text, extracts complete <li> items,
   routes them via TEMPLATE_REGISTRY, and appends to DOM via JavaScript
3. _finalize() handles completion — skips content replace for registered
   templates (scaffold + streamed items are already correct)
"""

from __future__ import annotations

import json

from nicegui import ui

from ui.stream_buffer import StreamBuffer
from ui.stream_handlers import (
    STATIC_TEMPLATES,
    TEMPLATE_REGISTRY,
    parse_first_line_value,
    route_stream_item,
)


class OutputPanel:
    """Claude analysis results display with streaming support."""

    def __init__(self, controller: object) -> None:
        with ui.card().classes("w-full"):
            ui.label("Analysis Output").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.scroll_area().classes("w-full h-96 border rounded") as self._scroll:
                self._content = ui.html("").classes("prose max-w-none p-3")

        # Streaming state
        self._buffer = StreamBuffer()
        self._template_type: str | None = None
        self._first_line_received: bool = False

        # Wire callbacks on controller
        controller.on_stream_chunk = lambda chunk: self.handle_stream_chunk(chunk)  # type: ignore[attr-defined]
        controller.on_processing_complete = lambda result: self._finalize(result)  # type: ignore[attr-defined]

    def setup_template(self, template_type: str) -> None:
        """Install scaffold HTML and configure buffer for a template type.

        Called before streaming begins (from on_template_setup callback).
        """
        self._template_type = template_type
        self._first_line_received = False

        # Get pattern from registry (or default)
        config = TEMPLATE_REGISTRY.get(template_type)
        pattern = config["pattern"] if config else r"<li[^>]*>.*?</li>"

        # Reset buffer with template-specific pattern
        self._buffer = StreamBuffer(pattern=pattern)

        # Install scaffold HTML
        scaffold = STATIC_TEMPLATES.get(template_type, STATIC_TEMPLATES["generic"])
        self._content.set_content(scaffold)

    def handle_stream_chunk(self, chunk: str) -> None:
        """Process a streaming chunk: buffer, extract, route, append.

        Thread-safe: buffer operations are lock-protected internally.
        UI updates use ui.run_javascript() which is safe from any thread.
        """
        if not self._template_type:
            # No template set up — fall back to raw append
            current = self._content.content or ""
            self._content.set_content(current + chunk)
            self._scroll.scroll_to(percent=1.0)
            return

        config = TEMPLATE_REGISTRY.get(self._template_type)
        if not config:
            # Unregistered template type — raw append
            current = self._content.content or ""
            self._content.set_content(current + chunk)
            self._scroll.scroll_to(percent=1.0)
            return

        text = chunk

        # Handle first-line parsing (e.g., sentiment overall value)
        flp = config.get("first_line_parser")
        if flp and not self._first_line_received:
            value, text = parse_first_line_value(text, config)
            if value:
                self._first_line_received = True
                callback_method = flp.get("callback_method")
                if callback_method == "set_overall_sentiment":
                    escaped = json.dumps(value)
                    ui.run_javascript(
                        f'document.getElementById("overall-sentiment-value").innerText = {escaped}'
                    )
                if not text.strip():
                    return

        if not text.strip():
            return

        # Extract complete items from buffer
        items = self._buffer.write_and_extract(text)

        # Route and append each item
        for item in items:
            routed = route_stream_item(item, config)
            if routed:
                list_id, item_html = routed
                self._append_to_dom(list_id, item_html)

        if items:
            self._scroll.scroll_to(percent=1.0)

    def _append_to_dom(self, list_id: str, item_html: str) -> None:
        """Append an HTML item to a target element via JavaScript."""
        # Escape for JS template literal
        escaped = item_html.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        ui.run_javascript(
            f'document.getElementById("{list_id}").insertAdjacentHTML("beforeend", `{escaped}`)'
        )

    def _finalize(self, result: dict) -> None:
        """Called when streaming is complete.

        For registered templates: scaffold + streamed items are already
        in the DOM — do NOT replace content (would destroy streamed items).
        For unregistered templates: replace with final result.
        """
        if self._template_type and self._template_type in TEMPLATE_REGISTRY:
            # Streaming already populated the DOM — just scroll
            self._scroll.scroll_to(percent=1.0)
            return

        if "result" in result:
            self._content.set_content(result["result"])
        self._scroll.scroll_to(percent=1.0)

    def clear(self) -> None:
        """Clear the output panel and reset streaming state."""
        self._content.set_content("")
        self._template_type = None
        self._first_line_received = False
        self._buffer.clear()
```

**Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_output_panel.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
./scripts/wsl-git.sh add ui/components/output_panel.py tests/test_output_panel.py
./scripts/wsl-git.sh commit -m "feat(DAR2-37): rewrite NiceGUI OutputPanel with streaming buffer pipeline"
```

---

## Task 4: Wire `on_template_setup` into PromptButtons

**Files:**
- Modify: `ui/components/prompt_buttons.py` (update `_run_prompt` to pass `on_template_setup`)
- Modify: `ui/pages/meeting_page.py` (pass `OutputPanel` reference to `PromptButtons`)
- Test: `tests/test_prompt_buttons.py` (add test for template setup wiring)

The critical gap: `PromptButtons._run_prompt()` calls `controller.run_prompt(template)` without `on_template_setup`, so `controller.template_type` is never set and the OutputPanel never gets a scaffold. We need to:
1. Give `PromptButtons` a reference to the `OutputPanel`
2. Look up `PromptConfig.template_type` from the `PROMPT_REGISTRY`
3. Pass an `on_template_setup` callback that calls `output_panel.setup_template()`

**Step 1: Write the failing test**

```python
# Add to tests/test_prompt_buttons.py (or create if needed)
"""Tests for PromptButtons template setup wiring (DAR2-37)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestPromptButtonsTemplateSetup:
    """Verify PromptButtons passes on_template_setup to controller."""

    def test_run_prompt_passes_template_setup(self) -> None:
        with patch("ui.components.prompt_buttons.ui"):
            from ui.components.prompt_buttons import PromptButtons

            controller = MagicMock()
            output_panel = MagicMock()
            buttons = PromptButtons(controller, output_panel=output_panel)

            # Simulate a known template from PROMPT_REGISTRY
            from prompts.templates import MEETING_SUMMARY_PROMPT

            import asyncio
            asyncio.get_event_loop().run_until_complete(
                buttons._run_prompt(MEETING_SUMMARY_PROMPT)
            )

            # Verify run_prompt was called with on_template_setup
            controller.run_prompt.assert_called_once()
            call_kwargs = controller.run_prompt.call_args
            assert call_kwargs.kwargs.get("on_template_setup") is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_prompt_buttons.py::TestPromptButtonsTemplateSetup -v`
Expected: TypeError — `PromptButtons.__init__()` doesn't accept `output_panel`

**Step 3: Update PromptButtons**

Modify `ui/components/prompt_buttons.py`:

```python
"""Context-aware prompt buttons (DAR2-26, DAR2-37).

Mid-meeting prompts (MEETING_ACTIVE only):
- Problem-solving, evaluate, analyze, first principles, hypothesis

Post-meeting prompts (POST_MEETING only):
- Meeting summary, extract topics, action items, key decisions

Copy Transcript button (POST_MEETING only):
- Copies full meeting transcript to clipboard via navigator.clipboard API

Processing guard: all prompt buttons disabled while a prompt is executing.

DAR2-37: Passes on_template_setup callback to controller.run_prompt()
so the OutputPanel can install scaffold HTML before streaming begins.
"""

from __future__ import annotations

import json

from nicegui import ui

from prompts.registry import PROMPT_REGISTRY


# Build a lookup: prompt_template string -> template_type string
_TEMPLATE_TO_TYPE: dict[str, str] = {
    cfg.template: cfg.template_type for cfg in PROMPT_REGISTRY
}


class PromptButtons:
    """Context-aware prompt buttons with processing guard."""

    def __init__(
        self,
        controller: object,
        *,
        output_panel: object | None = None,
    ) -> None:
        self._controller = controller
        self._output_panel = output_panel
        self._prompt_buttons: list[ui.button] = []

        # Mid-meeting prompts (hidden by default)
        with ui.card().classes("w-full") as self._mid_meeting_card:
            ui.label("Meeting Analysis").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.row().classes("gap-2 flex-wrap"):
                for name, template in self._mid_meeting_prompts():
                    btn = ui.button(
                        name,
                        on_click=lambda t=template: self._run_prompt(t),
                    ).classes("bg-blue-600 text-white")
                    self._prompt_buttons.append(btn)
        self._mid_meeting_card.set_visibility(False)

        # Post-meeting prompts (hidden by default)
        with ui.card().classes("w-full") as self._post_meeting_card:
            ui.label("Post-Meeting Analysis").classes(
                "text-sm font-semibold text-gray-500 uppercase tracking-wide"
            )
            with ui.row().classes("gap-2 flex-wrap"):
                for name, template in self._post_meeting_prompts():
                    btn = ui.button(
                        name,
                        on_click=lambda t=template: self._run_prompt(t),
                    ).classes("bg-purple-600 text-white")
                    self._prompt_buttons.append(btn)

                # Copy Transcript button
                self._copy_btn = ui.button(
                    "Copy Transcript",
                    on_click=self._copy_transcript,
                    icon="content_copy",
                ).classes("bg-gray-600 text-white")
        self._post_meeting_card.set_visibility(False)

    def _make_template_setup(self, prompt_template: str):
        """Create the on_template_setup callback for a prompt template.

        Returns a callable that:
        1. Looks up template_type from PROMPT_REGISTRY
        2. Calls output_panel.setup_template() to install scaffold HTML
        3. Returns template_type for controller to store
        """
        if self._output_panel is None:
            return None

        def on_template_setup(pt: str) -> str | None:
            template_type = _TEMPLATE_TO_TYPE.get(pt)
            if template_type and self._output_panel is not None:
                self._output_panel.setup_template(template_type)  # type: ignore[attr-defined]
            return template_type

        return on_template_setup

    async def _run_prompt(self, template: str) -> None:
        """Run prompt with processing guard — disables all prompt buttons."""
        self._set_buttons_enabled(False)
        try:
            self._controller.run_prompt(  # type: ignore[attr-defined]
                template,
                on_template_setup=self._make_template_setup(template),
            )
        finally:
            self._set_buttons_enabled(True)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable all prompt buttons."""
        for btn in self._prompt_buttons:
            btn.set_enabled(enabled)

    async def _copy_transcript(self) -> None:
        """Copy full meeting transcript to clipboard (json.dumps for JS safety)."""
        transcript = self._controller.get_meeting_transcript()  # type: ignore[attr-defined]
        if transcript:
            await ui.run_javascript(
                f"navigator.clipboard.writeText({json.dumps(transcript)})"
            )
            ui.notify("Transcript copied to clipboard", type="positive")
        else:
            ui.notify("No transcript available", type="warning")

    def set_state(self, state: str) -> None:
        """Show/hide prompt cards based on meeting state."""
        self._mid_meeting_card.set_visibility(state == "active")
        self._post_meeting_card.set_visibility(state == "post_meeting")

    @staticmethod
    def _mid_meeting_prompts() -> list[tuple[str, str]]:
        """Prompts available during active meeting."""
        return [
            ("Evaluate Problem", "evaluate_problem"),
            ("Analyze Statement", "analyze_statement"),
            ("First Principles", "first_principles"),
            ("Hypothesis", "hypothesis"),
        ]

    @staticmethod
    def _post_meeting_prompts() -> list[tuple[str, str]]:
        """Prompts available after meeting ends."""
        return [
            ("Meeting Summary", "meeting_summary"),
            ("Extract Topics", "extract_topics"),
            ("Action Items", "action_items"),
            ("Key Decisions", "key_decisions"),
        ]
```

**Step 4: Update meeting_page.py to pass output_panel to PromptButtons**

```python
# ui/pages/meeting_page.py — change line 39-42:
# BEFORE:
#   prompts = PromptButtons(controller)
#   OutputPanel(controller)
# AFTER:
            output = OutputPanel(controller)
            prompts = PromptButtons(controller, output_panel=output)
```

Note: `OutputPanel` must be created BEFORE `PromptButtons` now (output wires `on_stream_chunk` on the controller, and PromptButtons needs a reference to it). The layout order is: CaptureButtons, then output (Analysis Output card), then prompts. This changes the visual order slightly — output panel before prompt buttons. If visual order must remain the same, use NiceGUI's `move()` to reorder after creation.

**Step 5: Run tests to verify they pass**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/test_prompt_buttons.py tests/test_output_panel.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
./scripts/wsl-git.sh add ui/components/prompt_buttons.py ui/pages/meeting_page.py tests/test_prompt_buttons.py
./scripts/wsl-git.sh commit -m "feat(DAR2-37): wire on_template_setup from PromptButtons to OutputPanel"
```

---

## Task 5: Run Full Test Suite and Verify No Regressions

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run pytest tests/ -v --tb=short`
Expected: All tests pass, no regressions in existing tests

**Step 2: Run linting**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run ruff check ui/stream_buffer.py ui/components/output_panel.py ui/components/prompt_buttons.py ui/stream_handlers.py ui/pages/meeting_page.py`
Expected: No errors

**Step 3: Run type checking**

Run: `cd /mnt/c/Users/stwgre/Github/Darin_AA/claude-redesign && uv run mypy ui/stream_buffer.py ui/components/output_panel.py ui/components/prompt_buttons.py --ignore-missing-imports`
Expected: No errors (or only pre-existing NiceGUI typing issues)

**Step 4: Fix any issues found, then commit**

```bash
./scripts/wsl-git.sh add -A
./scripts/wsl-git.sh commit -m "chore(DAR2-37): fix lint and type issues"
```

---

## Summary of Changes

| File | Action | Purpose |
|------|--------|---------|
| `ui/stream_buffer.py` | CREATE | Thread-safe buffer + regex extraction (shared by PyQt6 + NiceGUI) |
| `ui/stream_handlers.py` | MODIFY | Add `STATIC_TEMPLATES` dict (data-driven scaffold registry) |
| `ui/components/output_panel.py` | REWRITE | Streaming pipeline: scaffold → buffer → extract → route → DOM append |
| `ui/components/prompt_buttons.py` | MODIFY | Pass `on_template_setup` callback to `controller.run_prompt()` |
| `ui/pages/meeting_page.py` | MODIFY | Wire `OutputPanel` reference into `PromptButtons` |
| `tests/test_stream_buffer.py` | CREATE | 9 tests for buffer extraction logic |
| `tests/test_static_templates.py` | CREATE | 3 tests verifying scaffold ↔ registry consistency |
| `tests/test_output_panel.py` | REWRITE | 10 tests for streaming OutputPanel |
| `tests/test_prompt_buttons.py` | MODIFY | 1 test for template setup wiring |
