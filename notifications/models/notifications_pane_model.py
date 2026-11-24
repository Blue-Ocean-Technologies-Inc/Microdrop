# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the notifications pane: the notifications, the
contributed sections above them, and the user's requests on them."""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Event,
    HasTraits,
    Instance,
    List,
    Property,
    Str,
)

# Local imports.
from ..consts import NotificationSection
from .notification import Notification
from .notification_center import NotificationCenter


class NotificationsPaneModel(HasTraits):
    """What the notifications pane shows."""

    #: The notifications.
    center = Instance(NotificationCenter, ())

    #: The contributed sections, in any order.
    sections = List(Instance(NotificationSection))

    #: The sections in the order shown, top first.
    ordered_sections = Property(
        List(Instance(NotificationSection)), observe="sections.items.order"
    )

    #: One line above the list, e.g. "2 new of 14".
    header_text = Property(Str, observe="center.[unread_count, entries.items]")

    #: Whether the notifications drawer is open.
    is_open = Bool(False)

    mark_all_read_button = Button()
    clear_all_button = Button()
    close_button = Button()

    #: Fired with the entry the user dismissed.
    dismiss = Event(Instance(Notification))

    #: Fired with the entry whose action button the user pressed.
    run_action = Event(Instance(Notification))

    def _get_ordered_sections(self):
        return sorted(self.sections, key=lambda section: section.order)

    def _get_header_text(self):
        total = len(self.center.entries)
        unread = self.center.unread_count

        if not total:
            return "No notifications"

        if unread:
            return f"{unread} new of {total}"

        return f"{total} notification{'s' if total > 1 else ''}"

    def expand_section(self, section_id):
        """Expand the section with ``section_id``, if there is one."""

        for section in self.sections:
            if section.id == section_id:
                section.expanded = True
