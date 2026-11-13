# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Select and More buttons for finger users of the protocol tree.

A finger has no Ctrl/Shift to build a multi-step selection and no right
click for the row menu. Select makes each tap toggle its row in the
selection; More opens the same row menu right-click opens, for the
selection. Both show only while Touch mode is on.
"""

# Enthought library imports.
from pyface.qt.QtCore import QEvent, Qt
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

# Microdrop package imports.
from microdrop_application.helpers import is_touch_mode

# Microdrop style imports.
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.colors import ACCENT_COLOR, WHITE
from microdrop_style.icons.icons import ICON_CHECKLIST, ICON_MORE_VERT
from microdrop_style.touch_style import TOUCH_RADIUS_PX, TOUCH_TARGET_PX

#: Pixel size of the button glyphs.
TOUCH_TREE_TOOL_GLYPH_PX = 24

SELECT_TOOLTIP = (
    "Select several steps: while on, each tap adds or removes a step "
    "instead of replacing the selection"
)
MORE_TOOLTIP = "Step actions for the selection (the right-click menu)"

_CHECKED_STYLE = f"""
QToolButton:checked {{
    border-radius: {TOUCH_RADIUS_PX}px;
    background-color: {ACCENT_COLOR};
    color: {WHITE};
}}
"""


class TouchTreeTools(QWidget):
    """The Select toggle, the selected-step count while it is on, and the
    More button, for one ProtocolTreeWidget.

    The widget itself always stays shown (empty and zero-sized while Touch
    mode is off) so it gets the StyleChange event every widget gets when
    Touch mode flips, and re-reads the mode then.
    """

    def __init__(self, tree_widget, parent=None):
        super().__init__(parent)
        self._tree_widget = tree_widget

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.select_button = self._make_button(ICON_CHECKLIST, SELECT_TOOLTIP)
        self.select_button.setCheckable(True)
        self.select_button.setStyleSheet(_CHECKED_STYLE)
        self.select_button.toggled.connect(tree_widget.set_multi_select)
        self.select_button.toggled.connect(self._update_count)

        self.count_label = QLabel()
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.more_button = self._make_button(ICON_MORE_VERT, MORE_TOOLTIP)
        self.more_button.setEnabled(tree_widget.can_show_row_menu())
        self.more_button.clicked.connect(
            lambda: tree_widget.show_row_menu_above(self.more_button)
        )

        for widget in (self.select_button, self.count_label, self.more_button):
            layout.addWidget(widget)

        tree_widget.tree.selectionModel().selectionChanged.connect(self._update_count)
        tree_widget.structural_editable_changed.connect(self.more_button.setEnabled)

        self._follow_touch_mode()

    @staticmethod
    def _make_button(glyph, tooltip):
        button = QToolButton()
        button.setText(glyph)
        button.setToolTip(tooltip)

        font = QFont(ICON_FONT_FAMILY)
        font.setPixelSize(TOUCH_TREE_TOOL_GLYPH_PX)
        button.setFont(font)
        # Fixed: Qt sizes a ligature glyph by its name's letters otherwise.
        button.setFixedSize(TOUCH_TARGET_PX, TOUCH_TARGET_PX)

        return button

    def event(self, event):
        if event.type() == QEvent.Type.StyleChange:
            self._follow_touch_mode()

        return super().event(event)

    def _follow_touch_mode(self):
        """Show the buttons in Touch mode; leaving it ends Select mode too,
        keeping the selection."""
        touch = is_touch_mode()

        if not touch:
            self.select_button.setChecked(False)

        self.select_button.setVisible(touch)
        self.more_button.setVisible(touch)
        self._update_count()

    def _update_count(self, *_):
        selecting = self.select_button.isChecked()
        count = len(self._tree_widget.tree.selectionModel().selectedRows(0))

        self.count_label.setText(f"{count} selected")
        self.count_label.setVisible(selecting)
