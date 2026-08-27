# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont, QIcon
from pyface.qt.QtWidgets import QApplication

from .button_styles import get_button_style, get_tooltip_style
from .combo_box_style import get_combobox_style
from .font_paths import load_font_and_get_family
from .general_style import get_general_style
from .label_style import get_label_style
from .message_box_style import get_message_box_style

QT_THEME_NAMES = {Qt.ColorScheme.Dark: "dark", Qt.ColorScheme.Light: "light"}


def is_dark_mode():
    return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def style_app(app_instance: "QApplication"):
    # Load the icon fonts (Material Symbols + Pictogrammers' Material
    # Design Icons — the latter has no ligatures, use \U000Fxxxx codepoints)
    load_font_and_get_family("material_symbols")
    load_font_and_get_family("material_design_icons")
    # load inter font and set with some size
    LABEL_FONT_FAMILY = load_font_and_get_family("inter")

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
