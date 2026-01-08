from traits.api import Str, UUID, This, Interface, List


class IStep(Interface):
    id = UUID
    name = Str
    parent = This


class IGroupStep(IStep):
    children = List(IStep)

    def add_step(self, step):
        """Routine for adding a step to this group"""

    def insert_step(self, idx, step):
        """Routine for inserting a step to this group at a specific idx"""

    def remove_step(self, step):
        """Routine for removing a step"""
