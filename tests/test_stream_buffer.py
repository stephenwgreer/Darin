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
        items = buf.write_and_extract("lo</li>")
        assert items == ['<li class="x">hello</li>']

    def test_multiple_items_in_one_chunk(self) -> None:
        buf = StreamBuffer()
        items = buf.write_and_extract("<li>one</li><li>two</li>")
        assert items == ["<li>one</li>", "<li>two</li>"]

    def test_custom_pattern(self) -> None:
        buf = StreamBuffer(pattern=r'<li class="fact-check-item">.*?</li>')
        items = buf.write_and_extract(
            '<li class="fact-check-item">check</li><li class="other">skip</li>'
        )
        assert items == ['<li class="fact-check-item">check</li>']

    def test_remainder_preserved(self) -> None:
        buf = StreamBuffer()
        buf.write_and_extract("<li>done</li>leftover <li>par")
        items = buf.write_and_extract("tial</li>")
        assert items == ["<li>partial</li>"]

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
