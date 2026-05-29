"""Pure-rendering toolbar widget for the pluggable protocol tree.

Owns no state. Takes a sorted list of IQuickAction implementations and
produces one icon-font QToolButton per action, keyed by action_id.
The QuickActionsController (separate unit) drives click routing,
per-action enabled state, and keyboard-shortcut wiring.
"""

from typing import Dict, List

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import QHBoxLayout, QToolButton, QWidget

from microdrop_style.button_styles import ICON_FONT_FAMILY

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction


class QuickActionBar(QWidget):
    """Horizontal row of icon-only QToolButtons, one per action."""

    def __init__(self, actions: List[IQuickAction], parent: QWidget = None):
        super().__init__(parent)
        self.buttons: Dict[str, QToolButton] = {}
        sorted_actions = sorted(actions,
                                key=lambda a: (a.priority, a.action_id))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        icon_font = QFont(ICON_FONT_FAMILY)
        icon_font.setPixelSize(20)
        for action in sorted_actions:
            btn = QToolButton()
            btn.setText(action.icon_text)
            btn.setFont(icon_font)
            btn.setToolTip(action.tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            self.buttons[action.action_id] = btn
            layout.addWidget(btn)
        layout.addStretch()
