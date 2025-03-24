from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser, QScrollBar
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont

from ui.font_manager import FontManager
from ui.html_templates import (wrap_in_base_template, create_topic_section,
                             create_insight_list, create_error_message,
                             create_status_message)

class OutputPanel(QWidget):
    """Right panel containing output"""
    
    # Signal for updating HTML content in the main thread
    html_update = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OutputPanel")  # Set object name for CSS styling
        self.setup_ui()
        self._current_output = ""
        self._auto_scroll = True
        self._user_scrolled = False
        
        # Connect the HTML update signal
        self.html_update.connect(self._update_html_content)
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Processed output container
        output_label = QLabel("Output")
        output_label.setFont(FontManager.get_font(14, QFont.Weight.Normal))
        layout.addWidget(output_label)
        
        # Use QTextBrowser for HTML support
        self.output_text = QTextBrowser()
        self.output_text.setOpenExternalLinks(True)  # Allow clicking links
        self.output_text.setReadOnly(True)
        self.output_text.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        
        # Connect scrollbar signals
        self.output_text.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.output_text.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        
        # Set up the stylesheet for the output text
        self.output_text.setStyleSheet("""
            QTextBrowser {
                background-color: #2D2D30;
                color: #FFFFFF;
                border: none;
                padding: 10px;
                border-radius: 5px;
            }
            
            .output-container {
                margin: 10px;
                padding: 10px;
            }
            
            .topic-section {
                margin-bottom: 20px;
                padding: 15px;
                background-color: #252526;
                border-radius: 8px;
                border-left: 4px solid #3498db;
            }
            
            .topic-title {
                font-size: 24px;
                color: #FFFFFF;
                margin: 0 0 15px 0;
                padding-bottom: 8px;
                border-bottom: 1px solid #3498db;
            }
            
            .insight-block {
                margin: 15px 0;
                padding: 12px;
                background-color: #2D2D2D;
                border-radius: 6px;
            }
            
            .insight-header {
                font-size: 18px;
                color: #61AFEF;
                margin: 0 0 10px 0;
            }
            
            .insight-list {
                margin: 0;
                padding-left: 20px;
            }
            
            .insight-item {
                margin: 8px 0;
                line-height: 1.5;
                color: #D4D4D4;
            }
            
            .error-message {
                margin: 10px 0;
                padding: 12px;
                background-color: #442222;
                border-left: 4px solid #E74C3C;
                border-radius: 4px;
            }
            
            .error-text {
                color: #E74C3C;
                margin: 0;
            }
            
            .status-message {
                margin: 10px 0;
                padding: 12px;
                background-color: #2C3E50;
                border-left: 4px solid #3498DB;
                border-radius: 4px;
            }
            
            .status-text {
                color: #3498DB;
                margin: 0;
            }
            
            code {
                background-color: #2D2D2D;
                padding: 1px 3px;
                border-radius: 3px;
                font-family: monospace;
                color: #D4D4D4;
            }
            
            pre {
                background-color: #2D2D2D;
                padding: 8px;
                border-radius: 5px;
                margin: 5px 0;
                border: 1px solid #3E3E3E;
                overflow-x: auto;
            }
            
            a { 
                color: #61AFEF;
                text-decoration: none;
            }
            
            a:hover { 
                color: #89C7F7;
                text-decoration: underline;
            }
            
            .transcript-text {
                font-family: monospace;
                line-height: 1.5;
                white-space: pre-wrap;
                background-color: #252526;
                padding: 12px;
                border-radius: 5px;
                border-left: 4px solid #61AFEF;
                margin-bottom: 15px;
            }
        """)
        
        # Also set this panel's background a bit darker than the app's default background
        self.setStyleSheet("""
            QWidget#OutputPanel {
                background-color: #252526;
                border-radius: 5px;
            }
        """)
        
        layout.addWidget(self.output_text)
    
    def _on_scroll(self, value):
        """Handle manual scrolling"""
        scrollbar = self.output_text.verticalScrollBar()
        # Check if we're not at the bottom
        self._user_scrolled = value < scrollbar.maximum()
        
        # If user scrolls to bottom, resume auto-scrolling
        if value == scrollbar.maximum():
            self._user_scrolled = False
    
    def _on_range_changed(self, min_val, max_val):
        """Handle when the scrollbar range changes (new content added)"""
        scrollbar = self.output_text.verticalScrollBar()
        if self._user_scrolled:
            # Calculate and maintain the relative position
            current_value = scrollbar.value()
            scrollbar.setValue(current_value)
        elif self._auto_scroll:
            self._scroll_to_bottom()
    
    def set_output(self, text):
        """Set the output text as HTML"""
        self._current_output = text
        self._user_scrolled = False  # Reset scroll state when setting new content
        self.html_update.emit(wrap_in_base_template(text))
    
    def append_output(self, text):
        """Append text to the current output as HTML"""
        self._current_output += text
        self.html_update.emit(wrap_in_base_template(self._current_output))
    
    def set_error(self, message):
        """Display an error message"""
        self.set_output(create_error_message(message))
    
    def set_status(self, message):
        """Display a status message"""
        self.set_output(create_status_message(message))
    
    @pyqtSlot(str)
    def _update_html_content(self, html):
        """Update the HTML content in the main thread"""
        # Store the current scroll position and whether we were at bottom
        scrollbar = self.output_text.verticalScrollBar()
        current_value = scrollbar.value()
        was_at_bottom = current_value == scrollbar.maximum()
        
        # Update content
        self.output_text.setHtml(html)
        
        # Restore scroll position
        if self._user_scrolled and not was_at_bottom:
            scrollbar.setValue(current_value)
        elif was_at_bottom or self._auto_scroll:
            self._scroll_to_bottom()
    
    def _scroll_to_bottom(self):
        """Scroll the output text to the bottom"""
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())