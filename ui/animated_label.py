from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

from ui.font_manager import FontManager


class AnimatedLabel(QLabel):
    def __init__(self, text: str, parent: QLabel | None = None) -> None:
        super().__init__(parent)
        self.full_text: str = text
        self.current_text: str = ""
        self.current_index: int = 0
        self.cursor: str = "█"
        self.show_cursor: bool = True

        # Set up the timer for typing animation
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.update_text)
        self.typing_timer.start(100)  # Update every 100ms

        # Set up the timer for cursor blinking
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self.toggle_cursor)
        self.cursor_timer.start(500)  # Blink every 500ms

        # Set the font
        self.setFont(FontManager.get_font(18, QFont.Weight.Bold))

    def update_text(self) -> None:
        if self.current_index < len(self.full_text):
            self.current_text = self.full_text[: self.current_index + 1]
            self.current_index += 1
            self.setText(self.current_text + (self.cursor if self.show_cursor else ""))
        else:
            self.typing_timer.stop()
            self.setText(self.full_text + (self.cursor if self.show_cursor else ""))

    def toggle_cursor(self) -> None:
        self.show_cursor = not self.show_cursor
        if self.current_index < len(self.full_text):
            self.setText(self.current_text + (self.cursor if self.show_cursor else ""))
        else:
            self.setText(self.full_text + (self.cursor if self.show_cursor else ""))
