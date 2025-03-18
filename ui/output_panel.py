from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QSplitter
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor

from ui.font_manager import FontManager

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
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        self.output_text.setFont(FontManager.get_font(12, QFont.Weight.Normal))
        output_layout.addWidget(self.output_text)
        
        # Add containers to splitter
        self.vertical_splitter.addWidget(transcript_container)
        self.vertical_splitter.addWidget(output_container)
        
        # Set the ratio between transcript (1) and output (2)
        self.vertical_splitter.setStretchFactor(0, 1)  # Transcript takes 1/3
        self.vertical_splitter.setStretchFactor(1, 2)  # Output takes 2/3
        
        # Add splitter to layout
        layout.addWidget(self.vertical_splitter)
    
    def set_transcript(self, text):
        """Set the transcript text"""
        self.transcript_text.setPlainText(text)
    
    def set_output(self, text):
        """Set the processed output text"""
        self.output_text.setPlainText(text)
        
        # Scroll to the bottom
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_text.setTextCursor(cursor)
    
    def set_output_json(self, json_data):
        """Set the output to formatted JSON"""
        import json
        formatted_json = json.dumps(json_data, indent=2)
        self.set_output(formatted_json)
    
    def clear(self):
        """Clear both text fields"""
        self.transcript_text.clear()
        self.output_text.clear()