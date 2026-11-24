# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The plugin load list as the top section of the notifications pane.

Contributed to the notifications plugin's NOTIFICATION_SECTIONS extension
point; without that plugin the contribution is simply unused. The section's
summary follows the load records, and its contents — the load-status panel's
view — are built the first time it is expanded.
"""

# Enthought library imports.
from traits.api import Instance, observe

# Microdrop package imports.
from notifications.consts import NotificationSection

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import PluginLoadStatus

# Local imports.
from .consts import (
    LOAD_STATUS_SECTION_ID,
    LOAD_STATUS_SECTION_ORDER,
    LOAD_STATUS_SECTION_TITLE,
)
from .load_status_model import PluginLoadStatusPanelModel


class PluginLoadStatusSection(NotificationSection):
    """The load records as a notifications pane section."""

    id = LOAD_STATUS_SECTION_ID
    title = LOAD_STATUS_SECTION_TITLE
    order = LOAD_STATUS_SECTION_ORDER

    #: The load records — the application's ``plugin_load_status``.
    status = Instance(PluginLoadStatus, ())

    def _factory_default(self):
        return self.build_contents

    def build_contents(self, parent):
        """The load-status panel's view, embedded, first failure selected."""
        from .load_status_view import PluginLoadStatusView

        model = PluginLoadStatusPanelModel(status=self.status)
        ui = model.edit_traits(
            view=PluginLoadStatusView, kind="subpanel", parent=parent
        )
        model.select_first_failure()

        return ui

    @observe("status.summary")
    def _follow_summary(self, event):
        self.summary = self.status.summary
