from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

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
        
        # Use QWebEngineView for better HTML support
        self.output_text = QWebEngineView()
        self.output_text.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.output_text.setHtml("")
        
        # Set up the base HTML with styles
        base_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    background-color: #2D2D30;
                    color: #FFFFFF;
                    font-family: system-ui, -apple-system, sans-serif;
                    padding: 10px;
                    margin: 0;
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
                
                .insight-list {
                    margin: 0;
                    padding-left: 25px;
                    list-style-type: disc !important;
                }
                
                .insight-item {
                    margin: 12px 0;
                    line-height: 1.5;
                    color: #D4D4D4;
                    display: list-item !important;
                    list-style-type: disc !important;
                }
                
                #dynamic-content {
                    list-style-type: disc !important;
                }
                
                #dynamic-content li {
                    display: list-item !important;
                    list-style-type: disc !important;
                }
            </style>
        </head>
        <body>
            <div id="content"></div>
        </body>
        </html>
        """
        self.output_text.setHtml(base_html)
        
        # Also set this panel's background a bit darker than the app's default background
        self.setStyleSheet("""
            QWidget#OutputPanel {
                background-color: #252526;
                border-radius: 5px;
            }
        """)
        
        layout.addWidget(self.output_text)
    
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
        # Update the content div
        js = f'document.getElementById("content").innerHTML = `{html}`;'
        self.output_text.page().runJavaScript(js)
    
    def append_to_dynamic_content(self, content):
        """Append content to the dynamic-content section of the template"""
        # Ensure content has proper class and style for formatting
        if content.startswith("<li"):
            if "class=" not in content:
                content = content.replace("<li", '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
            elif 'style="' not in content:
                content = content.replace('class="', 'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
        
        # Use JavaScript to append the content to the dynamic-content element
        js = f'''
        var dynamicContent = document.getElementById("dynamic-content");
        if (dynamicContent) {{
            dynamicContent.insertAdjacentHTML("beforeend", `{content}`);
        }}
        '''
        self.output_text.page().runJavaScript(js)