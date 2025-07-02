from traits.api import Instance, Str, HasTraits, Tuple
from pyface.undo.abstract_command import AbstractCommand
from traits.observation.events import ListChangeEvent, TraitChangeEvent

class TraitChangeCommand(AbstractCommand):

    name = Str("Restore Trait State")

    event = Instance(TraitChangeEvent)

    def do(self):
        print(f"{self.event} added to the stack!")

    def undo(self):
        setattr(self.event.object, self.event.name, self.event.old)

class ListChangeCommand(AbstractCommand):

    name = Str("Restore List state")

    event = Instance(ListChangeEvent)

    def do(self):
        print(f"{self.event} added to the stack!")

    def undo(self):
        for _ in self.event.added:
            self.event.object.pop(self.event.index)
        for i, item in enumerate(self.event.removed):
            self.event.object.insert(self.event.index, item)
