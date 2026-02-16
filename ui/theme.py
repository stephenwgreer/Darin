"""Centralized theme configuration for Darin Audio Assistant

This module provides a single source of truth for all colors, spacing,
and typography used throughout the application.
"""

from dataclasses import dataclass
from typing import Final


@dataclass
class ColorPalette:
    """Color palette for the dark theme"""

    # Backgrounds
    bg_primary: str = "#1E1E1E"  # Main window background
    bg_secondary: str = "#252526"  # Panel backgrounds
    bg_tertiary: str = "#2D2D2D"  # Card/container backgrounds
    bg_hover: str = "#37373D"  # Button hover state
    bg_active: str = "#094771"  # Active/selected state

    # Text
    text_primary: str = "#CCCCCC"  # Main text
    text_secondary: str = "#9D9D9D"  # Secondary text
    text_tertiary: str = "#6E6E6E"  # Disabled/muted text
    text_bright: str = "#FFFFFF"  # Headings

    # Accents
    accent_primary: str = "#007ACC"  # Primary actions (blue)
    accent_success: str = "#89D185"  # Success states (green)
    accent_warning: str = "#CCA700"  # Warning states (orange)
    accent_danger: str = "#F48771"  # Danger actions (red)

    # Borders
    border_primary: str = "#454545"  # Default borders
    border_accent: str = "#007ACC"  # Highlighted borders

    # Shadows
    shadow_color: str = "rgba(0, 0, 0, 0.3)"


@dataclass
class Spacing:
    """Spacing constants for consistent layout"""

    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 20
    xxl: int = 24


@dataclass
class Typography:
    """Typography settings"""

    font_family: str = "Space Grotesk, Arial, sans-serif"
    font_size_sm: int = 11
    font_size_base: int = 14
    font_size_lg: int = 18
    font_size_xl: int = 24
    font_size_xxl: int = 28


# Singleton instances
COLORS: Final[ColorPalette] = ColorPalette()
SPACING: Final[Spacing] = Spacing()
FONTS: Final[Typography] = Typography()
