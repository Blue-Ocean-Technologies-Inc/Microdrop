from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont, QIcon
from pyface.qt.QtWidgets import QApplication

from .button_styles import get_button_style, get_tooltip_style
from .font_paths import load_material_symbols_font, load_inter_font

QT_THEME_NAMES = {
    Qt.ColorScheme.Dark: "dark",
    Qt.ColorScheme.Light: "light"
}

def is_dark_mode():
    return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

def style_app(app_instance: 'QApplication'):
    # Load the Material Symbols font
    load_material_symbols_font()
    # load inter font and set with some size
    LABEL_FONT_FAMILY = load_inter_font()

    app_instance.setFont(QFont(LABEL_FONT_FAMILY, 11))
    QIcon.setThemeName("Material Symbols Outlined")


def get_general_style(theme):
    """Defines the base background and text color for the window/container."""
    if theme == "dark":
        return """
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            font-family: "Inter", sans-serif; /* Optional global font */
        }
        """
    else:
        return """
        QWidget {
            background-color: #f0f0f0;
            color: #000000;
            font-family: "Inter", sans-serif;
        }
        """


def get_label_style(theme):
    """Specific overrides for QLabels (headers, etc)."""
    if theme == "dark":
        return """
        QLabel {
            color: #e0e0e0;
        }
        /* Example: Create a specific class for headers if needed */
        QLabel[class="header"] {
            color: #ffffff;
        }
        """
    else:
        return """
        QLabel {
            color: #333333;
        }
        QLabel[class="header"] {
            color: #000000;
        }
        """


def get_combobox_style(theme):
    """
    Complex styling for QComboBox.
    Note: Styling the drop-down arrow usually requires an image/icon.
    """
    if theme == "dark":
        colors = {
            "bg": "#3a3a3a",
            "border": "#555555",
            "text": "#ffffff",
            "selection": "#4a90e2",
            "hover": "#454545"
        }
    else:
        colors = {
            "bg": "#ffffff",
            "border": "#cccccc",
            "text": "#000000",
            "selection": "#0078d4",
            "hover": "#e6e6e6"
        }

    return f"""
    QComboBox {{
        background-color: {colors['bg']};
        color: {colors['text']};
    }}

    QComboBox:hover {{
        background-color: {colors['hover']};
        border-color: {colors['selection']};
    }}

    /* The drop-down list (popup) */
    QComboBox QAbstractItemView {{
        background-color: {colors['bg']};
        color: {colors['text']};
        selection-background-color: {colors['selection']};
        selection-color: white;
        border: 1px solid {colors['border']};
    }}
    """


def get_complete_stylesheet(theme="light", button_type="default"):
    """
    Combines all modular styles into one cohesive sheet.
    """
    # 1. Base components
    general = get_general_style(theme)
    labels = get_label_style(theme)
    combos = get_combobox_style(theme)

    # 2. Your existing components
    buttons = get_button_style(theme, button_type)
    tooltips = get_tooltip_style(theme)

    # 3. Combine them
    # Order matters slightly: General generic rules first, specific widgets last.
    return f"{general}\n{labels}\n{combos}\n{buttons}\n{tooltips}"
