# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the plugin load-status panel: the shared load records
plus the row the user selected and the details shown for it."""

# Enthought library imports.
from traits.api import HasTraits, Instance, Property, Str, observe

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import (
    LOAD_FAILED,
    LOAD_LOADED,
    PluginLoadRecord,
    PluginLoadStatus,
)


class PluginLoadStatusPanelModel(HasTraits):
    """The records the panel lists and the one it details."""

    #: The load records — the application's ``plugin_load_status``.
    status = Instance(PluginLoadStatus, ())

    #: The record selected in the table.
    selected = Instance(PluginLoadRecord)

    #: What the details area shows for the selected record: the full
    #: traceback for a failure.
    details_text = Property(
        Str, observe="selected.[state, error, traceback, duration, essential]"
    )

    def _get_details_text(self):
        record = self.selected

        if record is None:
            return "Select a plugin to see its details."

        title = f"{record.name} ({record.plugin_id})"

        if record.essential:
            title += ", essential"

        if record.state == LOAD_FAILED:
            return f"{title} failed to start:\n\n{record.traceback or record.error}"

        if record.state == LOAD_LOADED:
            return f"{title} started in {record.duration:.3f} s."

        return f"{title} is {record.state}."

    def select_first_failure(self):
        """Select the first failed record, if any and nothing is selected."""
        if self.selected is not None:
            return

        for record in self.status.records:
            if record.state == LOAD_FAILED:
                self.selected = record

                return

    @observe("status.records.items")
    def _clear_selection_of_dropped_record(self, event):
        """A record dropped from the list (its plugin unloaded) is no longer
        selectable."""
        if self.selected is not None and self.selected not in self.status.records:
            self.selected = None
