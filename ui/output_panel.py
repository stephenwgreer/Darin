import html

from PyQt6.QtCore import pyqtSignal, pyqtSlot
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.html_templates import (
    create_error_message,
    create_status_message,
    wrap_in_base_template,
)


class OutputPanel(QWidget):
    """Right panel containing output"""

    # Signal for updating HTML content in the main thread
    html_update = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OutputPanel")  # Set object name for CSS styling
        self.setup_ui()
        self._current_output: str = ""
        self._auto_scroll: bool = True
        self._user_scrolled: bool = False

        # Connect the HTML update signal
        self.html_update.connect(self._update_html_content)

    def setup_ui(self) -> None:
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
                padding: 5px;
                font-weight: 500;
            }
        """)
        self.title_label.setMaximumHeight(50)
        layout.addWidget(self.title_label)

        # Use QWebEngineView for better HTML support
        self.output_text = QWebEngineView()
        self.output_text.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        self.output_text.setHtml("")

        # Set up the base HTML with styles
        base_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    background-color: #252526;
                    color: #CCCCCC;
                    font-family: "Space Grotesk", Arial, sans-serif;
                    padding: 0px;
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
                    border-left: 4px solid #007ACC;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                }

                .topic-title {
                    font-size: 28px;
                    color: #FFFFFF;
                    margin: 0 0 20px 0;
                    padding-bottom: 12px;
                    border-bottom: 1px solid #007ACC;
                    font-weight: 500;
                }

                .insight-block {
                    margin: 15px 0;
                    padding: 16px;
                    background-color: #2D2D2D;
                    border-radius: 8px;
                    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
                }

                .insight-list {
                    margin: 0;
                    padding-left: 25px;
                    list-style-type: disc !important;
                }

                .insight-item {
                    margin: 16px 0;
                    line-height: 1.6;
                    color: #CCCCCC;
                    display: list-item !important;
                    list-style-type: disc !important;
                    font-size: 14px;
                }

                .insight-item::marker {
                    color: #007ACC;
                }

                #dynamic-content {
                    list-style-type: disc !important;
                }

                #dynamic-content li {
                    display: list-item !important;
                    list-style-type: disc !important;
                }

                #dynamic-content li::marker {
                    color: #007ACC;
                }

                .error-message {
                    margin: 20px;
                    padding: 16px;
                    background-color: #5A1D1D;
                    border-left: 4px solid #F48771;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                }

                .error-text {
                    color: #F48771;
                    font-size: 14px;
                    margin: 0;
                }

                .status-message {
                    margin: 20px;
                    padding: 16px;
                    background-color: #2D2D2D;
                    border-left: 4px solid #007ACC;
                    border-radius: 8px;
                    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
                }

                .status-text {
                    color: #CCCCCC;
                    font-size: 14px;
                    margin: 0;
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

    def set_output(self, text: str) -> None:
        """Set the output text as HTML"""
        self._current_output = text
        self._user_scrolled = False  # Reset scroll state when setting new content
        self.html_update.emit(wrap_in_base_template(text))

    def set_title(self, title: str) -> None:
        """Update the output panel title"""
        self.title_label.setText(title)

    def append_output(self, text: str) -> None:
        """Append text to the current output as HTML"""
        self._current_output += text
        self.html_update.emit(wrap_in_base_template(self._current_output))

    def set_error(self, message: str) -> None:
        """Display an error message"""
        self.set_output(create_error_message(message))

    def set_status(self, message: str) -> None:
        """Display a status message"""
        self.set_output(create_status_message(message))

    def set_overall_sentiment(self, sentiment_value: str) -> None:
        """Update the overall sentiment value in the sentiment analysis template"""
        # Escape for JavaScript string context to prevent injection
        escaped_value = html.escape(sentiment_value).replace('"', '\\"').replace("'", "\\'")
        js = f'document.getElementById("overall-sentiment-value").innerText = "{escaped_value}";'
        self.output_text.page().runJavaScript(js)

    @pyqtSlot(str)
    def _update_html_content(self, html: str) -> None:
        """Update the HTML content in the main thread"""
        # Update the content div
        js = f'document.getElementById("content").innerHTML = `{html}`;'
        self.output_text.page().runJavaScript(js)

    def append_to_dynamic_content(self, content: str) -> None:
        """Append content to the dynamic-content section of the template"""
        # Ensure content has proper class and style for formatting
        if content.startswith("<li"):
            if "class=" not in content:
                content = content.replace(
                    "<li",
                    '<li class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                )
            elif 'style="' not in content:
                content = content.replace(
                    'class="',
                    'class="insight-item" style="display: list-item !important; list-style-type: disc !important;"',
                )

        # Use JavaScript to append the content to the dynamic-content element
        js = f"""
        var dynamicContent = document.getElementById("dynamic-content");
        if (dynamicContent) {{
            dynamicContent.insertAdjacentHTML("beforeend", `{content}`);
        }}
        """
        self.output_text.page().runJavaScript(js)

    def append_to_list_by_id(self, list_id: str, item_html: str) -> None:
        """Append an HTML list item to a specific list using its ID, preserving internal HTML."""
        # Ensure it has a base class if none is provided, but preserve existing classes.
        if 'class="' not in item_html:
            item_html = item_html.replace("<li", '<li class="insight-item"')

        # Basic styling for all list items appended this way
        base_style = "display: list-item !important; margin-bottom: 10px;"  # Added margin-bottom

        # Inject base style, preserving existing styles if any
        if 'style="' in item_html:
            # Insert base style after existing style attribute
            item_html = item_html.replace('style="', f'style="{base_style} ', 1)
        else:
            # Add style attribute with base style
            if 'class="' in item_html:
                item_html = item_html.replace('class="', f'style="{base_style}" class="', 1)
            else:
                # Should not happen due to class check above, but as fallback
                item_html = item_html.replace("<li", f'<li style="{base_style}"')

        # Escape the item_html for safe insertion into JavaScript string
        escaped_item_html = item_html.replace("`", "\\`").replace("$", "\$")

        js = f'''
        var list = document.getElementById("{list_id}");
        if (list) {{
            list.insertAdjacentHTML("beforeend", `{escaped_item_html}`);
        }}
        '''
        self.output_text.page().runJavaScript(js)
