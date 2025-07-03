from traits.api import Instance, Str, Float
from pyface.undo.abstract_command import AbstractCommand
from traits.observation.events import ListChangeEvent, TraitChangeEvent
import time
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class TraitChangeCommand(AbstractCommand):

    name = Str("Restore Trait State")

    event = Instance(TraitChangeEvent)

    def do(self):
        self.timestamp = time.time()

    def undo(self):
        logger.info(f"Undoing set {self.event.name} on {self.event.object} from {self.event.old} to {self.event.new}")
        setattr(self.event.object, self.event.name, self.event.old)

class ListChangeCommand(AbstractCommand):

    name = Str("Restore List state")

    event = Instance(ListChangeEvent)

    timestamp = Float()

    def do(self):
        self.timestamp = time.time()

    def merge(self, other):
        merge_timestamp = time.time()
        
        if isinstance(other, ListChangeCommand) and other.event.object == self.event.object and merge_timestamp - self.timestamp <= 1.5:
            if len(self.event.removed) == 0 and len(other.event.removed) == 0: # Only added
                self.event.added.extend(other.event.added)
                return True
        
        return False

    def undo(self):
        logger.info(f"Undoing list mod {self.event.object}, added {self.event.added}, removed {self.event.removed} at {self.event.index}")
        for _ in self.event.added:
            self.event.object.pop(self.event.index)
        for item in reversed(self.event.removed):
            self.event.object.insert(self.event.index, item)
