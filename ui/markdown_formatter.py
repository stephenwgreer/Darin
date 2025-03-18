import re

class MarkdownFormatter:
    @staticmethod
    def markdown_to_html(text):
        """Convert markdown text to HTML"""
        if not text:
            return ""
            
        # Bold text
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
        
        # Italic text
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)
        
        # Code blocks with language
        text = re.sub(r'```(\w+)\n(.*?)```', lambda m: f'<pre><code class="language-{m.group(1)}">{m.group(2)}</code></pre>', text, flags=re.DOTALL)
        
        # Code blocks without language
        text = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
        
        # Inline code
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
        
        # Headers
        text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        
        # Bullet points
        text = re.sub(r'^\* (.*?)$', r'• \1<br>', text, flags=re.MULTILINE)
        text = re.sub(r'^- (.*?)$', r'• \1<br>', text, flags=re.MULTILINE)
        
        # Numbered lists
        text = re.sub(r'^\d+\. (.*?)$', r'<br>\1<br>', text, flags=re.MULTILINE)
        
        # Links
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
        
        # Paragraphs
        text = re.sub(r'\n\n', r'<br><br>', text)
        
        return text 