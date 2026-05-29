"""QuickActionsController wires a QuickActionBar to a pane:

* On every ``pane.selection_changed`` / ``pane.protocol_running_changed``
  emission, walks the actions and calls ``button.setEnabled(...)``.
* Clicks route through ``_execute(action)`` which builds a fresh
  ``QuickActionCtx`` and calls ``action.on_execute_action(ctx)``,
  swallowing any exception so a buggy contribution can't crash the bar.
* When ``is_running == True``, the whole bar is disabled regardless of
  each action's ``is_enabled``.
"""

from unittest.mock import MagicMock

from pyface.qt.QtCore import QObject, Signal

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.views.quick_action_bar import (
    QuickActionBar, QuickActionsController,
)


class _FakePane(QObject):
    """Minimal stand-in for ProtocolTreePane."""
    selection_changed = Signal()
    protocol_running_changed = Signal(bool)

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager or MagicMock()
        # Controller pulls `pane.manager.selection` to build ctx.selected_paths.
        self.manager.selection = []


class _ToggleAction(BaseQuickAction):
    """is_enabled flips with the .enabled flag; on_execute_action
    bumps a counter and stashes the ctx for assertions."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.enabled = True
        self.calls = 0
        self.last_ctx = None

    def is_enabled(self, ctx) -> bool:
        return self.enabled

    def on_execute_action(self, ctx):
        self.calls += 1
        self.last_ctx = ctx


def test_initial_state_uses_is_enabled(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    b = _ToggleAction(action_id="b", icon_text="del", tooltip="")
    b.enabled = False
    pane = _FakePane()
    bar = QuickActionBar(actions=[a, b])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a, b])
    ctrl.refresh_enabled()
    assert bar.buttons["a"].isEnabled() is True
    assert bar.buttons["b"].isEnabled() is False


def test_protocol_running_disables_whole_bar(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    pane = _FakePane()
    bar = QuickActionBar(actions=[a])
    QuickActionsController(bar=bar, pane=pane, actions=[a])
    pane.protocol_running_changed.emit(True)
    assert bar.buttons["a"].isEnabled() is False
    pane.protocol_running_changed.emit(False)
    assert bar.buttons["a"].isEnabled() is True


def test_selection_changed_re_evaluates_is_enabled(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    pane = _FakePane()
    bar = QuickActionBar(actions=[a])
    QuickActionsController(bar=bar, pane=pane, actions=[a])
    a.enabled = False
    pane.selection_changed.emit()
    assert bar.buttons["a"].isEnabled() is False


def test_click_calls_execute_with_ctx_carrying_selection(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    pane = _FakePane()
    pane.manager.selection = [(0,), (1, 2)]
    bar = QuickActionBar(actions=[a])
    QuickActionsController(bar=bar, pane=pane, actions=[a])
    bar.buttons["a"].click()
    assert a.calls == 1
    assert a.last_ctx.pane is pane
    assert a.last_ctx.selected_paths == ((0,), (1, 2))
    assert a.last_ctx.is_running is False


def test_click_on_disabled_button_does_not_execute(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    a.enabled = False
    pane = _FakePane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a])
    ctrl.refresh_enabled()
    bar.buttons["a"].click()
    assert a.calls == 0


def test_controller_skips_actions_not_in_bar_buttons(qapp):
    """If QuickActionBar dropped a duplicate, the controller's iteration
    must NOT raise KeyError. It silently skips actions whose action_id
    isn't a key in bar.buttons."""
    a = _ToggleAction(action_id="dup", icon_text="add", tooltip="")
    b = _ToggleAction(action_id="dup", icon_text="del", tooltip="")
    pane = _FakePane()
    bar = QuickActionBar(actions=[a, b])      # bar drops the second
    # Controller must accept the full actions list without raising.
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a, b])
    ctrl.refresh_enabled()
    pane.protocol_running_changed.emit(True)
    pane.protocol_running_changed.emit(False)
    pane.selection_changed.emit()
    # Clicking the (only) button fires only the first action.
    bar.buttons["dup"].click()
    assert a.calls == 1
    assert b.calls == 0


def test_buggy_action_does_not_break_other_buttons(qapp, caplog):
    class _Boom(BaseQuickAction):
        def on_execute_action(self, ctx):
            raise RuntimeError("kaboom")

    boom = _Boom(action_id="b", icon_text="del", tooltip="")
    good = _ToggleAction(action_id="g", icon_text="add", tooltip="")
    pane = _FakePane()
    bar = QuickActionBar(actions=[boom, good])
    QuickActionsController(bar=bar, pane=pane, actions=[boom, good])
    bar.buttons["b"].click()                  # raises internally
    bar.buttons["g"].click()                  # must still fire
    assert good.calls == 1
    assert any("kaboom" in r.message for r in caplog.records)
