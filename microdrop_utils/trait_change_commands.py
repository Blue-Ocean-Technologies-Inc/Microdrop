# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Undoable commands built from Traits container-change events.

A command replays the diff its event carried on the container as it exists on
its owner at undo/redo time, never on the container the event captured: a later
reassignment of the trait (``model.channels = {...}``) swaps in a new container
object, and an edit to the detached old one changes nothing visible.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.undo.api import AbstractCommand
from traits.api import Float, Instance, List, Str
from traits.observation.api import SetChangeEvent

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def live_container(captured):
    """Return the container its owner holds now for the trait that ``captured``
    (the TraitList/Set/DictObject a change event carries) was the value of.

    Falls back to ``captured`` itself once the owner has been garbage
    collected. Top-level container traits only: a container nested inside
    another (``List(List(...))``) reports the outer trait's owner and name.
    """
    owner = captured.object()

    if owner is None:
        return captured

    return getattr(owner, captured.name)


class SetChangeCommand(AbstractCommand):
    """Undo and redo the membership changes one or more set events carried."""

    name = Str("Restore Set state")

    #: The first event; later edits to the same set merge into ``event_stack``.
    event = Instance(SetChangeEvent)

    #: When the last merged edit happened, for the merge window.
    timestamp = Float()

    #: ``{"added", "removed"}`` per merged event, oldest first.
    event_stack = List()

    def do(self):
        self.timestamp = time.time()
        self.event_stack.append(
            {"added": self.event.added.copy(), "removed": self.event.removed.copy()}
        )

    def merge(self, other):
        """Absorb ``other`` when it edits the same set within 0.5 s."""
        merge_timestamp = time.time()

        if (
            isinstance(other, SetChangeCommand)
            and other.event.object is self.event.object
            and merge_timestamp - self.timestamp <= 0.5
        ):
            logger.debug(f"Merging {self.event} with {other.event}")
            self.event_stack.append(
                {
                    "added": other.event.added.copy(),
                    "removed": other.event.removed.copy(),
                }
            )
            self.timestamp = merge_timestamp

            return True

        return False

    def undo(self):
        container = live_container(self.event.object)

        for event in reversed(self.event_stack):
            logger.debug(
                f"Undoing set mod {container}, added {event['added']}, "
                f"removed {event['removed']}"
            )

            for item in event["added"]:
                container.discard(item)

            for item in event["removed"]:
                container.add(item)

    def redo(self):
        container = live_container(self.event.object)

        for event in self.event_stack:
            logger.debug(
                f"Redoing set mod {container}, added {event['added']}, "
                f"removed {event['removed']}"
            )

            for item in event["removed"]:
                container.discard(item)

            for item in event["added"]:
                container.add(item)
