# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What a deferred plugin's placeholder pane says while the plugin loads.

Qt-free: the message follows the plugin's load record, so the placeholder
turns into an error notice when the plugin fails to load.
"""

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance, Property, Str

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import LOAD_FAILED, PluginLoadRecord


class PlaceholderPaneModel(HasTraits):
    """A deferred dock pane, standing in until its plugin has loaded."""

    #: The title of the pane the placeholder stands in for.
    pane_name = Str()

    #: The load record of the plugin that contributes the pane.
    record = Instance(PluginLoadRecord)

    #: True once that plugin has failed to load.
    failed = Property(Bool, observe="record.state")

    #: The placeholder's text: loading, or why the plugin failed.
    message = Property(Str, observe="pane_name, record.[state, error]")

    def _get_failed(self):
        return self.record is not None and self.record.state == LOAD_FAILED

    def _get_message(self):
        if not self.failed:
            return f"Loading {self.pane_name}…"

        return (
            f"{self.pane_name} could not be loaded: {self.record.error}\n\n"
            "Click the plugin status icon in the status bar for details."
        )
