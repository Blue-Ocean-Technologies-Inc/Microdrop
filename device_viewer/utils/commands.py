from traits.api import Instance, Str, Float, List
from pyface.undo.abstract_command import AbstractCommand
from traits.observation.events import ListChangeEvent, TraitChangeEvent, DictChangeEvent
import time

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class TraitChangeCommand(AbstractCommand):

    name = Str("Restore Trait State")

    event = Instance(TraitChangeEvent)

    def do(self):
        pass

    def undo(self):
        logger.debug(f"Undoing set {self.event.name} on {self.event.object} from {self.event.old} to {self.event.new}")
        setattr(self.event.object, self.event.name, self.event.old)
    
    def redo(self):
        logger.debug(f"Redoing set {self.event.name} on {self.event.object} from {self.event.old} to {self.event.new}")
        setattr(self.event.object, self.event.name, self.event.new)

class ListChangeCommand(AbstractCommand):

    name = Str("Restore List state")

    event = Instance(ListChangeEvent)

    timestamp = Float()

    event_stack = List([]) # Mini stack for 

    def do(self):
        self.timestamp = time.time()
        self.event_stack.append({
            "index": self.event.index,
            "added": self.event.added.copy(),
            "removed": self.event.removed.copy()
        })

    def merge(self, other):
        merge_timestamp = time.time()
        
        # Merge edits to the same list within x seconds of each other. Could possibly cause weird side effects in the undo system, but this seems like an easy general case
        if isinstance(other, ListChangeCommand) and other.event.object is self.event.object and merge_timestamp - self.timestamp <= 0.5:
            logger.debug(f"Merging {self.event} with {other.event}")
            self.event_stack.append({
                "index": other.event.index,
                "added": other.event.added.copy(),
                "removed": other.event.removed.copy()
            })
            self.timestamp = merge_timestamp # Reset timestamp to now
            return True
        
        return False

    def undo(self):
        for event in reversed(self.event_stack):
            logger.debug(f"Undoing list mod {self.event.object}, added {event["added"]}, removed {event["removed"]} at {event["index"]}")
            for _ in event["added"]:
                self.event.object.pop(event["index"])
            for item in reversed(event["removed"]):
                self.event.object.insert(event["index"], item)

    def redo(self):
        for event in self.event_stack:
            logger.debug(f"Redoing list mod {self.event.object}, added {event["added"]}, removed {event["removed"]} at {event["index"]}")
            for _ in event["removed"]:
                self.event.object.pop(event["index"])
            for item in reversed(event["added"]):
                self.event.object.insert(event["index"], item)

class DictChangeCommand(AbstractCommand):

    name = Str("Restore Dict state")

    event = Instance(DictChangeEvent)

    def do(self):
        pass

    def undo(self):
        logger.debug(f"Undoing dict mod {self.event.object}, added {self.event.added}, removed {self.event.removed}")
        for key in self.event.added.keys():
            self.event.object.pop(key)
        for key, value in self.event.removed.items():
            self.event.object[key] = value

    def redo(self):
        logger.debug(f"Redoing dict mod {self.event.object}, added {self.event.added}, removed {self.event.removed}")
        for key in self.event.removed.keys():
            self.event.object.pop(key)
        for key, value in self.event.added.items():
            self.event.object[key] = value