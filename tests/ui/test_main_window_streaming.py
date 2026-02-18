"""
MainWindow Streaming Handler Tests

Tests HTML streaming parsing and buffer management:
- _extract_html_items() with various HTML patterns
- Streaming handlers with partial HTML chunks
- Buffer management with incomplete tags
- O(n) performance via io.StringIO
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for PyQt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qapp):
    """Create MainWindow instance for testing."""
    with (
        patch("ui.main_window.ContinuousRecorder"),
        patch("ui.main_window.ApiClient"),
        patch("ui.main_window.FontManager"),
        patch("ui.main_window.logger"),
    ):
        window = MainWindow()
        yield window
        window.close()


class TestExtractHtmlItemsBasic:
    """Test _extract_html_items() with basic patterns."""

    def test_extract_single_complete_item(self, main_window):
        """Test extracting a single complete <li> item."""
        with main_window._html_state_lock:
            items = main_window._extract_html_items("<li>Item 1</li>")
        assert len(items) == 1
        assert items[0] == "<li>Item 1</li>"

    def test_extract_multiple_complete_items(self, main_window):
        """Test extracting multiple complete <li> items."""
        with main_window._html_state_lock:
            items = main_window._extract_html_items("<li>Item 1</li><li>Item 2</li>")
        assert len(items) == 2
        assert items[0] == "<li>Item 1</li>"
        assert items[1] == "<li>Item 2</li>"

    def test_extract_item_with_attributes(self, main_window):
        """Test extracting <li> items with attributes."""
        with main_window._html_state_lock:
            items = main_window._extract_html_items('<li class="test">Item</li>')
        assert len(items) == 1
        assert 'class="test"' in items[0]

    def test_no_complete_items(self, main_window):
        """Test with no complete items returns empty list."""
        with main_window._html_state_lock:
            items = main_window._extract_html_items("<li>Incomplete")
        assert len(items) == 0

    def test_buffer_retains_incomplete_tag(self, main_window):
        """Test incomplete tag remains in buffer."""
        with main_window._html_state_lock:
            items = main_window._extract_html_items("<li>Incomplete")
            assert len(items) == 0
            buffer_content = main_window._buffer_io.getvalue()
            assert "<li>Incomplete" in buffer_content


class TestExtractHtmlItemsPartialChunks:
    """Test _extract_html_items() with partial HTML chunks."""

    def test_partial_tag_across_chunks(self, main_window):
        """Test handling of partial HTML tags across multiple chunks."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            # Chunk 1: Incomplete tag
            items1 = main_window._extract_html_items("<li>Item ")
            assert len(items1) == 0

            # Chunk 2: Complete the tag
            items2 = main_window._extract_html_items("1</li>")
            assert len(items2) == 1
            assert "Item 1" in items2[0]

    def test_multiple_chunks_building_items(self, main_window):
        """Test building multiple items across chunks."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            # Chunk 1: First complete item + partial second
            items1 = main_window._extract_html_items("<li>Item 1</li><li>Item ")
            assert len(items1) == 1
            assert "Item 1" in items1[0]

            # Chunk 2: Complete second item + partial third
            items2 = main_window._extract_html_items("2</li><li>Item ")
            assert len(items2) == 1
            assert "Item 2" in items2[0]

            # Chunk 3: Complete third item
            items3 = main_window._extract_html_items("3</li>")
            assert len(items3) == 1
            assert "Item 3" in items3[0]

    def test_nested_tags_in_item(self, main_window):
        """Test items with nested tags."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            html = "<li><strong>Bold</strong> text</li>"
            items = main_window._extract_html_items(html)
            assert len(items) == 1
            assert "<strong>Bold</strong>" in items[0]

    def test_multiline_items(self, main_window):
        """Test items spanning multiple lines."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            html = """<li>
Line 1
Line 2
</li>"""
            items = main_window._extract_html_items(html)
            assert len(items) == 1
            assert "Line 1" in items[0]
            assert "Line 2" in items[0]


class TestExtractHtmlItemsCustomPatterns:
    """Test _extract_html_items() with custom regex patterns."""

    def test_custom_pattern_class_specific(self, main_window):
        """Test extraction with class-specific pattern."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            html = '<li class="fact-check-item">Fact</li><li class="other">Other</li>'
            items = main_window._extract_html_items(
                html, r'<li class=["\']fact-check-item["\']>.*?</li>'
            )
            assert len(items) == 1
            assert "fact-check-item" in items[0]

    def test_custom_pattern_multiple_classes(self, main_window):
        """Test extraction with pattern matching multiple classes."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            html = '<li class="answer-item">Answer</li><li class="rationale-item">Rationale</li><li class="other">Other</li>'
            items = main_window._extract_html_items(
                html, r'<li class=["\'](?:answer-item|rationale-item)["\']>.*?</li>'
            )
            assert len(items) == 2
            assert any("answer-item" in item for item in items)
            assert any("rationale-item" in item for item in items)


class TestBufferManagement:
    """Test buffer management and O(n) performance characteristics."""

    def test_buffer_cleared_after_extraction(self, main_window):
        """Test buffer is cleared after extracting items."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            # Add complete item
            items = main_window._extract_html_items("<li>Item 1</li>")
            assert len(items) == 1

            # Buffer should be empty after extraction
            buffer_content = main_window._buffer_io.getvalue()
            assert buffer_content == ""

    def test_buffer_retains_partial_after_extraction(self, main_window):
        """Test buffer retains partial content after extracting complete items."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            # Add complete item + partial
            items = main_window._extract_html_items("<li>Complete</li><li>Partial")
            assert len(items) == 1

            # Buffer should only contain partial
            buffer_content = main_window._buffer_io.getvalue()
            assert buffer_content == "<li>Partial"

    def test_buffer_handles_large_items(self, main_window):
        """Test buffer handles large HTML items efficiently."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            # Create large item (1000 chars)
            large_content = "x" * 1000
            html = f"<li>{large_content}</li>"

            items = main_window._extract_html_items(html)
            assert len(items) == 1
            assert large_content in items[0]

    def test_buffer_io_fresh_instance_after_extraction(self, main_window):
        """Test _buffer_io gets fresh instance after extraction to ensure clean state."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()
            original_buffer = main_window._buffer_io

            # Extract items
            main_window._extract_html_items("<li>Item</li>")

            # Buffer should be a new instance
            assert main_window._buffer_io is not original_buffer


class TestStreamingHandlersEdgeCases:
    """Test edge cases in streaming handlers."""

    def test_empty_chunk(self, main_window):
        """Test handling of empty text chunk."""
        with main_window._html_state_lock:
            items = main_window._extract_html_items("")
        assert len(items) == 0

    def test_whitespace_only_chunk(self, main_window):
        """Test handling of whitespace-only chunk."""
        with main_window._html_state_lock:
            items = main_window._extract_html_items("   \n\t  ")
        assert len(items) == 0

    def test_malformed_html_no_closing_tag(self, main_window):
        """Test handling of malformed HTML without closing tag."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            items = main_window._extract_html_items("<li>Unclosed item")
            assert len(items) == 0
            # Malformed HTML stays in buffer
            buffer_content = main_window._buffer_io.getvalue()
            assert "<li>Unclosed item" in buffer_content

    def test_html_entities_in_content(self, main_window):
        """Test handling of HTML entities in content."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            html = "<li>Item with &amp; entity</li>"
            items = main_window._extract_html_items(html)
            assert len(items) == 1
            assert "&amp;" in items[0]

    def test_special_characters_in_content(self, main_window):
        """Test handling of special characters in content."""
        with main_window._html_state_lock:
            # Clear buffer first
            main_window._buffer_io = __import__("io").StringIO()

            html = "<li>Item with < > \" ' characters</li>"
            items = main_window._extract_html_items(html)
            assert len(items) == 1


class TestOnStreamUpdateSignal:
    """Test on_stream_update slot handler."""

    def test_skip_status_messages(self, main_window):
        """Test status messages are skipped."""
        # Should not raise errors
        main_window.on_stream_update("Generating insights...")
        main_window.on_stream_update("Processing topic...")

    def test_stream_update_without_template_type(self, main_window):
        """Test stream update when template_type not set."""
        # Should handle gracefully without template type
        main_window._template_type = None
        # Should not raise errors
        main_window.on_stream_update("<li>Test</li>")

    def test_stream_update_with_unknown_template(self, main_window):
        """Test stream update with unknown template type."""
        with main_window._html_state_lock:
            main_window._template_type = "unknown-template"
        # Should fall through to default behavior without errors
        main_window.on_stream_update("<li>Test</li>")


class TestSentimentAnalysisStreaming:
    """Test sentiment analysis specific streaming behavior."""

    def test_overall_sentiment_extraction(self, main_window):
        """Test extraction of overall sentiment value."""
        with main_window._html_state_lock:
            main_window._template_type = "sentiment-analysis"
            main_window._overall_sentiment_received = False

        # Send sentiment value
        main_window.on_stream_update("Positive\n")

        # Check sentiment was received
        with main_window._html_state_lock:
            assert main_window._overall_sentiment_received is True

    def test_sentiment_only_accepted_values(self, main_window):
        """Test only Positive/Negative/Neutral are accepted as sentiment."""
        with main_window._html_state_lock:
            main_window._template_type = "sentiment-analysis"
            main_window._overall_sentiment_received = False

        # Send invalid sentiment
        main_window.on_stream_update("InvalidSentiment\n")

        # Should not be accepted
        with main_window._html_state_lock:
            assert main_window._overall_sentiment_received is False

    def test_sentiment_list_items_after_value(self, main_window):
        """Test list items are processed after sentiment value."""
        with main_window._html_state_lock:
            main_window._template_type = "sentiment-analysis"
            main_window._overall_sentiment_received = False

        # Send sentiment
        main_window.on_stream_update("Positive\n<li>Moment 1</li>")

        # Sentiment should be received
        with main_window._html_state_lock:
            assert main_window._overall_sentiment_received is True
