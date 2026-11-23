# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications pane: a header with Mark all read and Clear all, the
contributed sections, then the notifications, newest first.

Runs standalone against just its model::

    NotificationsPaneModel().configure_traits(view=NotificationsView)

(the buttons then do nothing: NotificationsController acts on them).
"""

# Enthought library imports.
from traitsui.api import HGroup, UItem, VGroup, View, spring

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_DELETE_SWEEP, ICON_DONE_ALL

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import IconButtonEditor

# Local imports.
from .notification_list_editor import NotificationListEditor
from .sections_editor import SectionsEditor

NotificationsView = View(
    VGroup(
        HGroup(
            UItem("header_text", style="readonly"),
            spring,
            UItem(
                "mark_all_read_button",
                editor=IconButtonEditor(glyph=ICON_DONE_ALL, tooltip="Mark all read"),
            ),
            UItem(
                "clear_all_button",
                editor=IconButtonEditor(
                    glyph=ICON_DELETE_SWEEP, tooltip="Clear all notifications"
                ),
            ),
        ),
        UItem("ordered_sections", editor=SectionsEditor()),
        UItem("center", editor=NotificationListEditor(), springy=True),
    ),
    resizable=True,
    width=380,
    height=640,
    title="Notifications",
)
