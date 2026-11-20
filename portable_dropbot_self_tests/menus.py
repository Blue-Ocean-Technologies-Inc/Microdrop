# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Tools > Self Tests... entry: opens the hub panel on the plugin's
session-long model."""

# Enthought library imports.
from envisage.api import Plugin
from pyface.action.api import Action
from pyface.tasks.action.api import SGroup
from traits.api import Instance

# Local imports.
from .consts import PKG
from .views.self_tests_view import self_tests_view


class SelfTestsAction(Action):
    """Open the self-test hub, non-modal; a second click brings the open
    panel to the front instead of opening another."""

    id = f"{PKG}.self_tests"
    name = "&Self Tests..."
    tooltip = "Run the Portable DropBot self-tests and save their report"

    #: The plugin whose controller opens the panel (made in its start()).
    plugin = Instance(Plugin)

    def perform(self, event):
        controller = self.plugin.controller

        if controller.is_panel_open():
            # TraitsUI's UI has no raise / activate call, nor has pyface for a
            # TraitsUI window: the Qt widget is the only handle.
            controller.info.ui.control.raise_()
            controller.info.ui.control.activateWindow()

            return

        task = getattr(event, "task", None)
        parent = task.window.control if task is not None else None

        controller.edit_traits(view=self_tests_view, parent=parent)


def self_tests_group_factory(plugin):
    """The Tools menu group of the hub."""

    return SGroup(SelfTestsAction(plugin=plugin), id=f"{PKG}.self_tests_group")
