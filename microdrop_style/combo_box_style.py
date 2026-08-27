# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

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