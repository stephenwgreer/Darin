from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QTextBrowser, QSplitter
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor

from ui.font_manager import FontManager
from ui.markdown_formatter import MarkdownFormatter

class OutputPanel(QWidget):
    """Right panel containing transcript and processed output"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Create vertical splitter for transcript and output
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.setHandleWidth(5)  # Make splitter handle more visible
        
        # Transcript container
        transcript_container = QWidget()
        transcript_layout = QVBoxLayout(transcript_container)
        
        transcript_label = QLabel("Transcript")
        transcript_label.setFont(FontManager.get_font(14, QFont.Weight.Normal))
        transcript_layout.addWidget(transcript_label)
        
        self.transcript_text = QTextEdit()
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setMinimumHeight(100)
        self.transcript_text.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        transcript_layout.addWidget(self.transcript_text)
        
        # Processed output container
        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        
        output_label = QLabel("Processed Output")
        output_label.setFont(FontManager.get_font(14, QFont.Weight.Normal))
        output_layout.addWidget(output_label)
        
        # Use QTextBrowser instead of QTextEdit for rich text support
        self.output_text = QTextBrowser()
        self.output_text.setOpenExternalLinks(True)  # Allow clicking links
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        self.output_text.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        
        # Set up the stylesheet for the output text
        self.output_text.setStyleSheet("""
            QTextBrowser {
                background-color: #1E1E1E;
                color: #FFFFFF;
            }
            QTextBrowser code {
                background-color: #2D2D2D;
                padding: 1px 3px;
                border-radius: 3px;
                font-family: monospace;
                color: #D4D4D4;
            }
            QTextBrowser pre {
                background-color: #2D2D2D;
                padding: 8px;
                border-radius: 5px;
                margin: 5px 0;
                border: 1px solid #3E3E3E;
            }
            QTextBrowser h1 { 
                font-size: 24px; 
                margin: 8px 0 4px 0;
                color: #FFFFFF;
            }
            QTextBrowser h2 { 
                font-size: 20px; 
                margin: 6px 0 3px 0;
                color: #FFFFFF;
            }
            QTextBrowser h3 { 
                font-size: 16px; 
                margin: 4px 0 2px 0;
                color: #FFFFFF;
            }
            QTextBrowser p {
                margin: 3px 0;
            }
            QTextBrowser ul, QTextBrowser ol {
                margin: 3px 0;
                padding-left: 20px;
            }
            QTextBrowser li {
                margin: 2px 0;
            }
            QTextBrowser a { 
                color: #61AFEF;
            }
            QTextBrowser a:hover { 
                color: #89C7F7;
            }
        """)
        
        output_layout.addWidget(self.output_text)
        
        # Add containers to splitter
        self.vertical_splitter.addWidget(transcript_container)
        self.vertical_splitter.addWidget(output_container)
        
        # Set the ratio between transcript (1) and output (2)
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 2)  # Output takes 2/3
        
        # Add splitter to layout
        layout.addWidget(self.vertical_splitter)
    
    def set_transcript(self, text):
        """Set the transcript text"""
        self.transcript_text.setPlainText(text)
    
    def set_output(self, text):
        """Set the processed output text with markdown formatting"""
        html_text = MarkdownFormatter.markdown_to_html(text)
        self.output_text.setHtml(html_text)
        
        # Scroll to the bottom
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_text.setTextCursor(cursor)
    
    def set_output_json(self, json_data):
        """Set the output to formatted JSON"""
        import json
        formatted_json = json.dumps(json_data, indent=2)
        self.set_output(f"```json\n{formatted_json}\n```")
    
    def clear(self):
        """Clear both text fields"""
        self.transcript_text.clear()
        self.output_text.clear()