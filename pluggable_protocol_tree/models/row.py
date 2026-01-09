from traits.api import HasTraits, Instance, Str, List, provides, UUID, Float

from pluggable_protocol_tree.interfaces.i_row import IRow, IGroupRow


@provides(IRow)
class BaseRow(HasTraits):
    id = UUID()
    name = Str("Step")
    duration = Float(1.0)
    parent = Instance(IRow)


@provides(IGroupRow)
class GroupRow(BaseRow):
    children = List(IRow)

    def add_row(self, row):
        row.parent = self
        self.children.append(row)

    def insert_row(self, idx, row):
        row.parent = self
        self.children.insert(idx, row)

    def remove_row(self, row):
        if row in self.children:
            self.children.remove(row)
            row.parent = None


class ActionRow(BaseRow):
    """
    Dummy class to inject with further columns
    """

    pass
