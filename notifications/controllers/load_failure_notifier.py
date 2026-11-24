# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Post an error notification for every plugin that fails to load.

Reads the application's plugin load records (``microdrop_utils``), which
every plugin loader writes, so failures from before this plugin started are
posted too. Load records change on the GUI thread only.
"""

# Enthought library imports.
from traits.api import HasTraits, Instance, observe

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import LOAD_FAILED, PluginLoadStatus

# Local imports.
from ..consts import CATEGORY_PLUGINS, SEVERITY_ERROR
from ..models.notification_center import NotificationCenter

#: Who the failure notifications come from.
LOAD_FAILURE_SOURCE = "plugin loader"


class PluginLoadFailureNotifier(HasTraits):
    """Turns failed load records into notifications."""

    #: The load records — the application's ``plugin_load_status``.
    status = Instance(PluginLoadStatus)

    #: Where the notifications go.
    center = Instance(NotificationCenter)

    def traits_init(self):
        """Post the failures recorded before this notifier existed."""

        if self.status is None:
            return

        for record in self.status.records:
            self._post_if_failed(record)

    @observe("status:records:items:state")
    def _post_new_failure(self, event):
        self._post_if_failed(event.object)

    @observe("status:records:items:[error, traceback]")
    def _show_failure_detail(self, event):
        """A failure's state is set before its reason: the reason then
        fills in the entry already posted."""
        record = event.object
        entry = None if self.center is None else self.center.find(_key(record))

        if record.state == LOAD_FAILED and entry is not None:
            entry.detail = _detail(record)

    def _post_if_failed(self, record):
        if record.state != LOAD_FAILED or self.center is None:
            return

        self.center.post(
            f"{record.name or record.plugin_id} failed to load",
            detail=_detail(record),
            severity=SEVERITY_ERROR,
            category=CATEGORY_PLUGINS,
            source=LOAD_FAILURE_SOURCE,
            key=_key(record),
        )


def _key(record):
    return (CATEGORY_PLUGINS, record.plugin_id)


def _detail(record):
    return record.traceback or record.error
