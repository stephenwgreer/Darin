"""HTML templates and structure for output formatting."""

BASE_HTML_TEMPLATE = """
<div class="output-container">
    {content}
</div>
"""

TOPIC_TEMPLATE = """
<div class="topic-section">
    <h1 class="topic-title">{title}</h1>
    <div class="topic-content">
        {content}
    </div>
</div>
"""

INSIGHT_TEMPLATE = """
<div class="insight-block">
    <h2 class="insight-header">{header}</h2>
    <ul class="insight-list">
        {items}
    </ul>
</div>
"""

INSIGHT_ITEM_TEMPLATE = """
<li class="insight-item">{content}</li>
"""

ERROR_TEMPLATE = """
<div class="error-message">
    <p class="error-text">{message}</p>
</div>
"""

STATUS_TEMPLATE = """
<div class="status-message">
    <p class="status-text">{message}</p>
</div>
"""


def create_insight_list(items):
    """Create an HTML list from insight items."""
    items_html = "".join(INSIGHT_ITEM_TEMPLATE.format(content=item) for item in items)
    return INSIGHT_TEMPLATE.format(header="Insights", items=items_html)


def create_topic_section(title, content):
    """Create a topic section with title and content."""
    return TOPIC_TEMPLATE.format(title=title, content=content)


def wrap_in_base_template(content):
    """Wrap content in the base HTML template."""
    return BASE_HTML_TEMPLATE.format(content=content)


def create_error_message(message):
    """Create an error message display."""
    return ERROR_TEMPLATE.format(message=message)


def create_status_message(message):
    """Create a status message display."""
    return STATUS_TEMPLATE.format(message=message)
