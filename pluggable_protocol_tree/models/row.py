from traits.api import HasTraits, Instance, Str, List, provides, Float, Property

from pluggable_protocol_tree.interfaces.i_row import IRow, IGroupRow


@provides(IRow)
class BaseRow(HasTraits):
    id = Property(Str)
    name = Str("Step")
    duration_s = Float(1.0)
    parent = Instance(IRow)

    def _get_id(self):
        indices = []
        current_row = self

        while current_row.parent:
            try:
                # Add 1 because users expect 1-based indexing
                idx = current_row.parent.children.index(current_row) + 1
                indices.insert(0, str(idx))
            except ValueError:
                break
            current_row = current_row.parent

        return ".".join(indices) if indices else ""


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
    Dummy class to inject with further columns.
    """
    pass
