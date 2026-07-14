"""Shortcut wiring lives in QuickActionsController. For every action
whose ``shortcut`` is non-empty we register one widget-scoped QShortcut
on the pane, routed through ``_execute`` so it respects ``is_enabled``
and the ``is_running`` gate. Two actions declaring the same key:
the second registration is skipped and a warning is logged."""

from pyface.qt.QtCore import QObject, Qt, Signal
from pyface.qt.QtGui import QKeySequence

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.views.quick_action_bar import (
    QuickActionBar, QuickActionsController,
)


class _Pane(QObject):
    selection_changed = Signal()
    protocol_running_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        from unittest.mock import MagicMock
        self.manager = MagicMock()
        self.manager.selection = []


class _FakeDockPane:
    """Stand-in for PluggableProtocolDockPane exposing the tree pane."""

    def __init__(self, pane):
        self._pane = pane


class _Counting(BaseQuickAction):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = 0

    def on_execute_action(self, ctx):
        self.calls += 1


def test_shortcut_registers_widget_scoped_qshortcut(qapp):
    a = _Counting(action_id="r", icon_text="summarize", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, dock_pane=_FakeDockPane(pane), actions=[a])
    assert len(ctrl.shortcuts) == 1
    qs = ctrl.shortcuts[0]
    assert qs.key() == QKeySequence("R")
    assert qs.context() == Qt.WidgetWithChildrenShortcut
    assert qs.parent() is pane


def test_shortcut_triggers_execute(qapp):
    a = _Counting(action_id="r", icon_text="summarize", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, dock_pane=_FakeDockPane(pane), actions=[a])
    ctrl.shortcuts[0].activated.emit()
    assert a.calls == 1


def test_shortcut_is_gated_by_is_running(qapp):
    a = _Counting(action_id="r", icon_text="summarize", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, dock_pane=_FakeDockPane(pane), actions=[a])
    pane.protocol_running_changed.emit(True)
    ctrl.shortcuts[0].activated.emit()
    assert a.calls == 0


def test_no_shortcut_means_no_qshortcut_registered(qapp):
    a = _Counting(action_id="r", icon_text="add", tooltip="", shortcut="")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, dock_pane=_FakeDockPane(pane), actions=[a])
    assert ctrl.shortcuts == []


def test_duplicate_shortcut_skips_second_and_logs_warning(qapp, caplog):
    a = _Counting(action_id="first", icon_text="add", tooltip="",
                  shortcut="R")
    b = _Counting(action_id="second", icon_text="del", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a, b])
    ctrl = QuickActionsController(bar=bar, dock_pane=_FakeDockPane(pane), actions=[a, b])
    # Only the first wins.
    assert len(ctrl.shortcuts) == 1
    ctrl.shortcuts[0].activated.emit()
    assert a.calls == 1
    assert b.calls == 0
    assert any(
        "R" in r.message and "first" in r.message and "second" in r.message
        for r in caplog.records)
