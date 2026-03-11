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
            self._buffer.write(text)
            content = self._buffer.getvalue()

            matches = list(re.finditer(self._pattern, content, re.DOTALL))
            if not matches:
                return []

            items = []
            last_end = 0
            remainder_parts = []
            for match in matches:
                items.append(match.group(0))
                remainder_parts.append(content[last_end : match.start()])
                last_end = match.end()
            remainder_parts.append(content[last_end:])
            self._buffer = io.StringIO("".join(remainder_parts))
            self._buffer.seek(0, 2)
            return items

    def clear(self) -> None:
        """Reset the buffer (call between prompts)."""
        with self._lock:
            self._buffer = io.StringIO()
