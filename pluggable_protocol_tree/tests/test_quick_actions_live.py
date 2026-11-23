# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Quick actions follow PROTOCOL_QUICK_ACTIONS contributions added or removed
while the app runs, as protocol columns do (#1062)."""

# Standard library imports.
from unittest.mock import MagicMock

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from envisage.api import Application, Plugin
from pyface.qt.QtCore import Signal
from pyface.qt.QtWidgets import QWidget
from traits.api import List

# Microdrop package imports.
from pluggable_protocol_tree.consts import PROTOCOL_QUICK_ACTIONS
from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from pluggable_protocol_tree.views.quick_action_bar import (
    QuickActionBar,
    QuickActionsController,
)


class QuickActionsContributingPlugin(Plugin):
    id = "test.quick_action_contributor"

    contributed_quick_actions = List(contributes_to=PROTOCOL_QUICK_ACTIONS)

    def _contributed_quick_actions_default(self):
        return [
            BaseQuickAction(action_id="save", priority=20),
            BaseQuickAction(action_id="add_step", priority=10),
        ]


class _LiveDockPane:
    """Records the action lists the plugin hands to the mounted pane."""

    def __init__(self):
        self.rebuilds = []

    def rebuild_quick_actions(self, actions):
        self.rebuilds.append([action.action_id for action in actions])


class _TreePane(QWidget):
    """The tree-pane surface the controller wires to."""

    selection_changed = Signal()
    protocol_running_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.manager = MagicMock()
        self.manager.selection = []


class _DockPane:
    def __init__(self, pane):
        self._pane = pane


class _CountingAction(BaseQuickAction):
    calls = List()

    def on_execute_action(self, ctx):
        self.calls.append(ctx)


@pytest.fixture
def tree_plugin(monkeypatch):
    """A started tree plugin whose dock pane is mounted, with no contributor."""
    # An envisage Application installs its preferences as the process-wide
    # default node; restore it so later PreferencesHelper tests don't share it.
    monkeypatch.setattr(package_globals, "_default_preferences", None)

    # The dramatiq actors and their broker are not under test.
    monkeypatch.setattr(PluggableProtocolTreePlugin, "_declare_listeners", _no_op)

    plugin = PluggableProtocolTreePlugin()
    plugin.live_dock_pane = _LiveDockPane()
    monkeypatch.setattr(
        PluggableProtocolTreePlugin,
        "_live_dock_pane",
        lambda self: self.live_dock_pane,
    )

    application = Application(plugins=[plugin])
    application.start()

    yield plugin

    application.stop()


def _no_op(*args):
    pass


def _action_ids(plugin):
    return [action.action_id for action in plugin._assemble_quick_actions()]


def test_a_contributor_added_after_the_tree_started_adds_its_actions(tree_plugin):
    contributor = QuickActionsContributingPlugin()

    assert _action_ids(tree_plugin) == []

    tree_plugin.application.add_plugin(contributor)

    assert _action_ids(tree_plugin) == ["add_step", "save"]
    assert tree_plugin.live_dock_pane.rebuilds == [["add_step", "save"]]


def test_a_removed_contributor_takes_its_actions_away(tree_plugin):
    contributor = QuickActionsContributingPlugin()
    tree_plugin.application.add_plugin(contributor)

    tree_plugin.application.remove_plugin(contributor)

    assert _action_ids(tree_plugin) == []
    assert tree_plugin.live_dock_pane.rebuilds[-1] == []


def test_the_bar_and_controller_swap_their_actions_in_place(qapp):
    first = _CountingAction(action_id="first", shortcut="F")
    second = _CountingAction(action_id="second", shortcut="S")
    pane = _TreePane()
    bar = QuickActionBar(actions=[first])
    controller = QuickActionsController(
        bar=bar, dock_pane=_DockPane(pane), actions=[first]
    )
    old_shortcuts = list(controller.shortcuts)

    bar.set_actions([first, second])
    controller.set_actions([first, second])
    bar.buttons["second"].click()

    assert set(bar.buttons) == {"first", "second"}
    assert len(second.calls) == 1
    assert len(controller.shortcuts) == 2
    assert not any(shortcut.isEnabled() for shortcut in old_shortcuts)

    bar.set_actions([second])
    controller.set_actions([second])

    assert set(bar.buttons) == {"second"}
    assert [shortcut.key().toString() for shortcut in controller.shortcuts] == ["S"]
