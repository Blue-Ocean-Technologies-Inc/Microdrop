# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One entry of the notifications pane. Qt-free."""

# Enthought library imports.
from traits.api import (
    Bool,
    Enum,
    Event,
    Float,
    HasTraits,
    Instance,
    Int,
    Property,
    Str,
    Tuple,
    Union,
    observe,
)

# Local imports.
from ..consts import SEVERITIES, OpenPathAction, PublishAction

#: A detail holding this reads as a traceback, shown monospace.
TRACEBACK_MARKER = "Traceback (most recent call last)"


class Notification(HasTraits):
    """A notification, or several identical ones collapsed into one."""

    #: Notifications with the same key collapse into this entry.
    key = Tuple()

    #: One line.
    title = Str()

    #: Longer text shown when the entry is expanded.
    detail = Str()

    severity = Enum(*SEVERITIES)

    #: Free text grouping, e.g. "log" or "plugins".
    category = Str()

    #: Who posted it: a plugin package or a logger name.
    source = Str()

    #: Seconds since the epoch of the first and the latest occurrence.
    first_seen = Float()
    last_seen = Float()

    #: How many times it occurred.
    count = Int(1)

    #: The entry's button, if any.
    action = Union(None, Instance(PublishAction), Instance(OpenPathAction))

    #: True until the user has seen it.
    unread = Bool(True)

    #: Whether the pane shows the detail. Kept with the entry so the list
    #: keeps it when its rows are rebuilt.
    expanded = Bool(False)

    #: True when the detail is a traceback, shown monospace and unwrapped.
    monospace_detail = Property(Bool, observe="detail")

    #: Fired when anything shown changes. One trait for a list to observe
    #: on each of its entries rather than seven: hundreds of entries each
    #: hooked seven times made posting slow.
    changed = Event()

    def _get_monospace_detail(self):
        return TRACEBACK_MARKER in self.detail

    @observe("title, detail, count, last_seen, unread, action, expanded")
    def _announce_change(self, event):
        self.changed = True
