# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One entry of the notifications drawer. Qt-free."""

# Enthought library imports.
from traits.api import (
    Any,
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
from ..consts import (
    SEVERITIES,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    HelpAction,
    OpenPathAction,
    PublishAction,
    SnoozeAction,
)

#: A detail holding this reads as a traceback, shown monospace.
TRACEBACK_MARKER = "Traceback (most recent call last)"

#: The first part of a thread's entry key: ``(THREAD_KEY, thread_id)``.
THREAD_KEY = "thread"


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

    #: The second, quieter button: a help link or "Later".
    secondary_action = Union(None, Instance(HelpAction), Instance(SnoozeAction))

    #: The user has to do something about it: listed under Needs attention.
    needs_attention = Bool(False)

    #: The condition that raised it; resolving that id clears it.
    condition_id = Str()

    #: Its declared notification category; empty when uncategorised.
    category_id = Str()

    #: True until the user has seen it.
    unread = Bool(True)

    #: Seen for the first time in the drawer open now; marked until it closes.
    is_new = Bool(False)

    #: What the user did with it, e.g. "Calibrate", or what resolved it;
    #: empty until then. Its buttons give way to this.
    acted = Str()

    #: Whether the drawer shows the whole detail. Kept with the entry so a
    #: rebuilt card keeps it.
    expanded = Bool(False)

    #: For a section's alert (never listed in Activity): the section's id
    #: and the SectionAlert it stands for.
    section_id = Str()
    alert = Any()

    #: The stripe ``(light theme, dark theme)`` instead of the severity's.
    accent = Tuple()

    #: True when the detail is a traceback, shown monospace and unwrapped.
    monospace_detail = Property(Bool, observe="detail")

    #: Whether its toast stays until dismissed or acted on.
    sticky = Property(Bool, observe="severity, action, needs_attention")

    #: Fired when anything shown changes. One trait for a card to observe
    #: rather than a dozen: hundreds of entries each hooked a dozen times
    #: made posting slow.
    changed = Event()

    def _get_monospace_detail(self):
        return TRACEBACK_MARKER in self.detail

    def _get_sticky(self):
        urgent = self.severity in (SEVERITY_WARNING, SEVERITY_ERROR)

        return urgent or self.needs_attention or self.action is not None

    @property
    def is_thread(self):
        """Whether it is a thread's entry, updated in place by each post."""
        return bool(self.key) and self.key[0] == THREAD_KEY

    @observe(
        "title, detail, severity, count, last_seen, unread, action,"
        " secondary_action, needs_attention, is_new, acted, expanded"
    )
    def _announce_change(self, event):
        self.changed = True
