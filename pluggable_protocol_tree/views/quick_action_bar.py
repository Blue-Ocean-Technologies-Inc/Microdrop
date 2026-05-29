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


# --- controller ----------------------------------------------------


from logger.logger_service import get_logger
from pluggable_protocol_tree.models.quick_action import QuickActionCtx

logger = get_logger(__name__)


class QuickActionsController:
    """Wires a QuickActionBar to a ProtocolTreePane.

    Listens for ``pane.selection_changed`` / ``pane.protocol_running_changed``
    and keeps ``button.setEnabled(...)`` in sync with each action's
    ``is_enabled(ctx)``. Routes clicks through ``_execute(action)`` so
    a buggy contribution can't crash the bar. Builds a fresh ctx on
    every call — never caches.
    """

    def __init__(self, *, bar: QuickActionBar, pane, actions):
        self._bar = bar
        self._pane = pane
        self._actions = list(actions)
        self._is_running = False
        # Wire button clicks.
        for action in self._actions:
            btn = bar.buttons[action.action_id]
            btn.clicked.connect(lambda _checked=False, a=action: self._execute(a))
        # Wire pane signals (drives re-enable + running state).
        pane.selection_changed.connect(self.refresh_enabled)
        pane.protocol_running_changed.connect(self._on_running_changed)
        self.refresh_enabled()

    def _build_ctx(self) -> QuickActionCtx:
        sel = tuple(tuple(p) for p in (self._pane.manager.selection or []))
        return QuickActionCtx(pane=self._pane,
                              selected_paths=sel,
                              is_running=self._is_running)

    def _on_running_changed(self, running: bool) -> None:
        self._is_running = bool(running)
        self.refresh_enabled()

    def refresh_enabled(self) -> None:
        ctx = self._build_ctx()
        for action in self._actions:
            try:
                enabled = bool(action.is_enabled(ctx)) and not ctx.is_running
            except Exception as e:                # pragma: no cover - defensive
                logger.warning(
                    f"is_enabled failed for {action.action_id!r}: {e}; "
                    f"disabling button.")
                enabled = False
            self._bar.buttons[action.action_id].setEnabled(enabled)

    def _execute(self, action) -> None:
        ctx = self._build_ctx()
        if ctx.is_running or not self._bar.buttons[action.action_id].isEnabled():
            # The shortcut path bypasses Qt's enabled-state gate; gate again here.
            return
        try:
            action.on_execute_action(ctx)
        except Exception as e:
            logger.error(
                f"quick-action {action.action_id!r} raised: {e}", exc_info=True)
