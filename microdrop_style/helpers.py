from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont, QIcon
from pyface.qt.QtWidgets import QApplication, QWidget

from .button_styles import get_complete_stylesheet
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

def update_qwidget_theme_styling(widget: 'QWidget', theme="light"):
    """Update styling of a qwidget"""
    button_style = get_complete_stylesheet(theme, "default")
    widget.setStyleSheet(button_style)