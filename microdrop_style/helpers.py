from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont, QIcon
from pyface.qt.QtWidgets import QApplication

from .button_styles import get_button_style, get_tooltip_style
from .combo_box_style import get_combobox_style
from .font_paths import load_material_symbols_font, load_inter_font
from .general_style import get_general_style
from .label_style import get_label_style
from .message_box_style import get_message_box_style

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

def get_complete_stylesheet(theme="light", button_type="default"):
    """
    Combines all modular styles into one cohesive sheet.
    """
    general = get_general_style(theme)
    labels = get_label_style(theme)
    combos = get_combobox_style(theme)
    buttons = get_button_style(theme, button_type)
    tooltips = get_tooltip_style(theme)
    message_box = get_message_box_style(theme)

    # Order matters slightly: General generic rules first, specific widgets last.
    return f"{general}\n{labels}\n{combos}\n{buttons}\n{tooltips}{message_box}"
