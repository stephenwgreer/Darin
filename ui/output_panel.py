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
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        layout.setSpacing(0)  # Remove spacing
        
        # Add title label
        self.title_label = QLabel("Output")
        self.title_label.setObjectName("output_title")
        self.title_label.setStyleSheet("""
            QLabel#output_title {
                font-size: 28px;
                color: #FFFFFF;
                padding: 20px;
                font-weight: 500;
            }
        """)
        layout.addWidget(self.title_label)
        
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
                    background-color: #252526;
                    color: #FFFFFF;
                    font-family: system-ui, -apple-system, sans-serif;
                    padding: 20px;
                    margin: 0;
                    font-size: 14px;
                }
                
                .output-container {
                    margin: 0;
                    padding: 0;
                }
                
                .topic-section {
                    margin-bottom: 24px;
                    padding: 20px;
                    background-color: #2D2D2D;
                    border-radius: 8px;
                    border-left: 4px solid #3498db;
                }
                
                .topic-title {
                    font-size: 28px;
                    color: #FFFFFF;
                    margin: 0 0 20px 0;
                    padding-bottom: 12px;
                    border-bottom: 1px solid #3498db;
                    font-weight: 500;
                }
                
                .insight-block {
                    margin: 15px 0;
                    padding: 16px;
                    background-color: #2D2D2D;
                    border-radius: 8px;
                }
                
                .insight-list {
                    margin: 0;
                    padding-left: 25px;
                    list-style-type: disc !important;
                }
                
                .insight-item {
                    margin: 16px 0;
                    line-height: 1.6;
                    color: #D4D4D4;
                    display: list-item !important;
                    list-style-type: disc !important;
                    font-size: 14px;
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
        
        # Remove the panel background
        self.setStyleSheet("""
            QWidget#OutputPanel {
                background-color: transparent;
            }
        """)
        
        layout.addWidget(self.output_text)
    
    def set_output(self, text):
        """Set the output text as HTML"""
        self._current_output = text
        self._user_scrolled = False  # Reset scroll state when setting new content
        self.html_update.emit(wrap_in_base_template(text))
    
    def set_title(self, title):
        """Update the output panel title"""
        self.title_label.setText(title)
    
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
    
    def set_overall_sentiment(self, sentiment_value):
        """Update the overall sentiment value in the sentiment analysis template"""
        js = f'document.getElementById("overall-sentiment-value").innerText = "{sentiment_value}";'
        self.output_text.page().runJavaScript(js)
    
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

    def append_to_list_by_id(self, list_id, item_html):
        """Append an HTML list item to a specific list using its ID."""
        # Ensure content has proper styling (non-bold for fill-gaps)
        if "class=" not in item_html:
            item_html = item_html.replace("<li", '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
        elif 'style="' not in item_html:
             # Add default style if only class exists
             item_html = item_html.replace('class="', 'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"')
        elif "font-weight: bold" in item_html:
             # Remove bold if it exists (specific case for potential copy-paste from other sections)
             item_html = item_html.replace(" font-weight: bold !important;", "")
             item_html = item_html.replace("font-weight: bold !important;", "")

        # Escape the item_html for safe insertion into JavaScript string
        escaped_item_html = item_html.replace('`', '\\`').replace('$', '\$')
        
        js = f'''
        var list = document.getElementById("{list_id}");
        if (list) {{
            list.insertAdjacentHTML("beforeend", `{escaped_item_html}`);
        }}
        '''
        self.output_text.page().runJavaScript(js)