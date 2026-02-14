import re

class SimpleListStreamHandler:
    """Handles streaming updates for templates that append to a single list."""

    def __init__(self, output_callback, bold_items=False):
        """
        Initializes the handler.

        Args:
            output_callback: Function to call when a complete list item is ready 
                             (e.g., output_panel.append_to_dynamic_content).
            bold_items: If True, adds a 'bold-list-item' class to extracted items.
        """
        self.output_callback = output_callback
        self.bold_items = bold_items
        self._html_buffer = ""

    def _extract_list_item(self, buffer):
        """Extracts the first complete <li>...</li> item from the buffer."""
        item_start = buffer.find("<li")
        if item_start == -1: return None
        item_end = buffer.find("</li>", item_start)
        if item_end == -1: return None
        return buffer[item_start : item_end + 5]

    def process_chunk(self, chunk: str):
        """Processes an incoming chunk of text, extracts complete list items, and calls the callback."""
        self._html_buffer += chunk
        while True:
            item = self._extract_list_item(self._html_buffer)
            if item is None:
                break  # No complete item found in the buffer yet

            # Remove the processed item from the buffer
            # Find the actual start position again in case of multiple items in one go
            item_start_pos = self._html_buffer.find(item)
            self._html_buffer = self._html_buffer[item_start_pos + len(item):]

            item_to_append = item
            # Add bold class if needed, ensuring not to duplicate if already present
            if self.bold_items:
                # Use regex to avoid issues if attributes exist
                if not re.search(r'''<li[^>]*class=['"].*bold-list-item.*['"]''', item):
                    if 'class=' in item:
                        item_to_append = item.replace('class="', 'class="bold-list-item ', 1)
                        item_to_append = item_to_append.replace("class='", "class='bold-list-item ", 1)
                    else:
                        item_to_append = item.replace('<li', '<li class="bold-list-item"', 1)
            
            # Call the callback with the processed item
            self.output_callback(item_to_append)