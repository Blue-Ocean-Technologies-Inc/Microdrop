"""Pure-rendering toolbar widget for the pluggable protocol tree.

Owns no state. Takes a sorted list of IQuickAction implementations and
produces one icon-font QToolButton per action, keyed by action_id.
The QuickActionsController (separate unit) drives click routing,
per-action enabled state, and keyboard-shortcut wiring.
"""

from typing import Dict, List

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont, QKeySequence, QShortcut
from pyface.qt.QtWidgets import QHBoxLayout, QToolButton, QWidget

from logger.logger_service import get_logger
from microdrop_style.button_styles import ICON_FONT_FAMILY

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction
from pluggable_protocol_tree.models.quick_action import QuickActionCtx

logger = get_logger(__name__)


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
            if action.action_id in self.buttons:
                logger.warning(
                    f"quick-action duplicate action_id {action.action_id!r}: "
                    f"keeping first contribution; skipping subsequent entry.")
                continue
            btn = QToolButton()
            btn.setText(action.icon_text)
            btn.setFont(icon_font)
            btn.setToolTip(action.tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            self.buttons[action.action_id] = btn
            layout.addWidget(btn)
        layout.addStretch()


# --- controller ----------------------------------------------------


class QuickActionsController:
    """Wires a QuickActionBar to the protocol dock pane.

    Takes the ``PluggableProtocolDockPane`` (the composition root) and
    reaches its tree pane via ``dock_pane._pane`` for the selection /
    running signals, ``manager.selection``, and the shortcut parent.
    Every ctx it builds carries the dock pane, so actions can reach both
    the tree pane (``ctx.pane``) and dock-level state such as the logging
    controller (``ctx.dock_pane.logging_controller``).

    Keeps ``button.setEnabled(...)`` in sync with each action's
    ``is_enabled(ctx)`` on ``selection_changed`` / ``protocol_running_changed``.
    Routes clicks through ``_execute(action)`` so a buggy contribution
    can't crash the bar. Builds a fresh ctx on every call — never caches.
    """

    def __init__(self, *, bar: QuickActionBar, dock_pane, actions):
        self._bar = bar
        self._dock_pane = dock_pane
        self._pane = dock_pane._pane
        self._actions = list(actions)
        self._is_running = False
        # Wire button clicks. Only wire the first action per action_id —
        # duplicate contributions were already dropped by QuickActionBar,
        # so iterating self._actions here (the full caller-supplied list)
        # could otherwise double-connect the same button for two actions
        # that share an id.
        _wired_ids: set = set()
        for action in self._actions:
            if action.action_id not in bar.buttons:
                continue
            if action.action_id in _wired_ids:
                continue
            _wired_ids.add(action.action_id)
            btn = bar.buttons[action.action_id]
            btn.clicked.connect(lambda _checked=False, a=action: self._execute(a))
        # Wire tree-pane signals (drives re-enable + running state).
        self._pane.selection_changed.connect(self.refresh_enabled)
        self._pane.protocol_running_changed.connect(self._on_running_changed)
        self.shortcuts = []
        self._wire_shortcuts()
        self.refresh_enabled()

    def _build_ctx(self) -> QuickActionCtx:
        sel = tuple(tuple(p) for p in (self._pane.manager.selection or []))
        return QuickActionCtx(dock_pane=self._dock_pane,
                              selected_paths=sel,
                              is_running=self._is_running)

    def _on_running_changed(self, running: bool) -> None:
        self._is_running = bool(running)
        self.refresh_enabled()

    def refresh_enabled(self) -> None:
        ctx = self._build_ctx()
        _seen: set = set()
        for action in self._actions:
            if action.action_id not in self._bar.buttons:
                continue
            if action.action_id in _seen:
                continue
            _seen.add(action.action_id)
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
        if action.action_id not in self._bar.buttons:
            return
        if ctx.is_running or not self._bar.buttons[action.action_id].isEnabled():
            # The shortcut path bypasses Qt's enabled-state gate; gate again here.
            return
        try:
            action.on_execute_action(ctx)
        except Exception as e:
            logger.error(
                f"quick-action {action.action_id!r} raised: {e}", exc_info=True)

    def _wire_shortcuts(self) -> None:
        claimed = {}                              # shortcut str -> action_id
        for action in self._actions:
            if action.action_id not in self._bar.buttons:
                continue
            key_str = (action.shortcut or "").strip()
            if not key_str:
                continue
            existing = claimed.get(key_str)
            if existing is not None:
                logger.warning(
                    f"quick-action shortcut conflict on {key_str!r}: "
                    f"{existing!r} already registered; skipping "
                    f"{action.action_id!r}.")
                continue
            claimed[key_str] = action.action_id
            qs = QShortcut(QKeySequence(key_str), self._pane)
            qs.setContext(Qt.WidgetWithChildrenShortcut)
            qs.activated.connect(lambda a=action: self._execute(a))
            self.shortcuts.append(qs)
