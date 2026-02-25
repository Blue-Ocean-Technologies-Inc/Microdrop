import time

from pyface.undo.abstract_command import AbstractCommand
from traits.api import Str, Instance, Float, List
from traits.observation._set_change_event import SetChangeEvent

import logging
logger = logging.getLogger(__name__)


class SetChangeCommand(AbstractCommand):

    name = Str("Restore Set state")

    event = Instance(SetChangeEvent)  # Assuming you have a SetChangeEvent

    timestamp = Float()

    event_stack = List([])  # Mini stack for merging

    def do(self):
        self.timestamp = time.time()
        # Sets have no indices, so we only track added/removed elements
        self.event_stack.append(
            {"added": self.event.added.copy(), "removed": self.event.removed.copy()}
        )

    def merge(self, other):
        merge_timestamp = time.time()

        # Merge edits to the same set within 0.5 seconds of each other.
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
            self.timestamp = merge_timestamp  # Reset timestamp to now
            return True

        return False

    def undo(self):
        # Reverse the stack so we undo the most recent changes first
        for event in reversed(self.event_stack):
            logger.debug(
                f"Undoing set mod {self.event.object}, added {event['added']}, removed {event['removed']}"
            )

            # To undo, we discard what was added...
            for item in event["added"]:
                self.event.object.discard(item)

                # ...and add back what was removed.
            for item in event["removed"]:
                self.event.object.add(item)

    def redo(self):
        for event in self.event_stack:
            logger.debug(
                f"Redoing set mod {self.event.object}, added {event['added']}, removed {event['removed']}"
            )

            # To redo, we discard what was originally removed...
            for item in event["removed"]:
                self.event.object.discard(item)

            # ...and add what was originally added.
            for item in event["added"]:
                self.event.object.add(item)
