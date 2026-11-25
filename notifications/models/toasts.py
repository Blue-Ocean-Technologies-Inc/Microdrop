# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The toasts on screen, Qt-free: what each shows, its time left, and
quiet mode."""

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance, Int, List, Property, Str

# Local imports.
from .notification import Notification
from .settings import NotificationSettings


class ToastItem(HasTraits):
    """One toast on screen."""

    #: The notification it shows.
    entry = Instance(Notification)

    #: Milliseconds left before it leaves on its own; sticky toasts keep it.
    remaining_ms = Int()

    #: While the pointer is over it, its time does not run.
    hovered = Bool(False)

    #: Set when it starts leaving; the view animates it out, then calls
    #: ``ToastStackModel.remove``.
    leaving = Bool(False)

    #: Where it goes when it leaves: into the bell (still unread), or simply
    #: away (acted on, dismissed from the list, or the drawer opened).
    into_bell = Bool(True)


class ToastStackModel(HasTraits):
    """The toasts on screen, oldest first, and the arrivals past the limit."""

    items = List(Instance(ToastItem))

    #: Whether and when toasts leave on their own, the sound, and the
    #: categories' choices.
    settings = Instance(NotificationSettings, ())

    #: Toasts that did not fit, gone straight to the bell since the stack
    #: was last empty, oldest first; and how many.
    overflow_entries = List(Instance(Notification))
    overflow = Property(Int, observe="overflow_entries.items")

    #: SOURCE OF TRUTH for quiet mode: while True only errors, Needs
    #: attention items and ``quiet_reason``'s own categories pop up; the
    #: rest are held for one summary toast when it ends.
    quiet = Bool(False)

    #: What runs while quiet, e.g. "Protocol": the summary says "Protocol
    #: finished", and that category group's notifications still pop up.
    quiet_reason = Str("Protocol")

    #: Entries held while quiet, oldest first.
    held = List(Instance(Notification))

    def _get_overflow(self):
        return len(self.overflow_entries)

    def entries_shown(self):
        """The entries on screen as toasts (leaving ones too, until they
        land)."""
        return [item.entry for item in self.items]

    def times_out(self, item):
        """Whether ``item`` leaves on its own: an info or success toast,
        while the settings say toasts time out."""
        return self.settings.auto_dismiss and not item.entry.sticky

    def progress(self, item):
        """``item``'s time left, 0-1; None when it does not time out."""

        if not self.times_out(item):
            return None

        return item.remaining_ms / max(self.settings.timeout_ms, 1)

    def find(self, entry):
        """The toast showing ``entry``, or None."""

        for item in self.items:
            if item.entry is entry:
                return item

        return None

    def remove(self, item):
        """Take a toast off, once it has left."""

        if item in self.items:
            self.items.remove(item)

        if not self.items:
            self.overflow_entries = []
