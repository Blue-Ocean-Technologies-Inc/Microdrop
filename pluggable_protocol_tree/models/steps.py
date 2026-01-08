from traits.api import HasTraits, Instance, Str, List, provides, UUID

from pluggable_protocol_tree.interfaces.i_step import IStep, IGroupStep


@provides(IStep)
class BaseStep(HasTraits):
    id = UUID()
    name = Str("Step")
    parent = Instance(IStep)


@provides(IGroupStep)
class GroupStep(BaseStep):
    children = List(IStep)

    def add_step(self, step):
        step.parent = self
        self.children.append(step)

    def insert_step(self, idx, step):
        step.parent = self
        self.children.insert(idx, step)

    def remove_step(self, step):
        if step in self.children:
            self.children.remove(step)
            step.parent = None


class ActionStep(BaseStep):
    """
    Dummy class to inject with further columns
    """

    pass
