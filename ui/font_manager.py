import os
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtCore import QDir

class FontManager:
    # List of preferred fonts in order
    FONT_PREFERENCES = [
        "Space Grotesk",
        "Arial"  # Fallback
    ]
    
    @classmethod
    def get_font(cls, size, weight=QFont.Weight.Normal):
        """Get the first available font from the preferences list"""
        for font_name in cls.FONT_PREFERENCES:
            font = QFont(font_name, size, weight)
            if font.exactMatch():
                return font
        
        # If no fonts match exactly, return the first one that exists
        for font_name in cls.FONT_PREFERENCES:
            # Check if the font exists in the system
            if font_name in QFontDatabase.families():
                return QFont(font_name, size, weight)
        
        # If all else fails, return Arial
        return QFont("Arial", size, weight)
    
    @classmethod
    def load_fonts(cls):
        """Load custom fonts from the assets/fonts directory"""
        font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
        if not os.path.exists(font_dir):
            os.makedirs(font_dir)
            return
        
        for filename in os.listdir(font_dir):
            if filename.endswith(('.ttf', '.otf')):
                font_path = os.path.join(font_dir, filename)
                QFontDatabase.addApplicationFont(font_path) 