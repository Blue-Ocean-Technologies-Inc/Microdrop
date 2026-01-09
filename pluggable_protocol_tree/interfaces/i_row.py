from traits.api import Str, UUID, This, Interface, List


class IRow(Interface):
    id = UUID
    name = Str
    parent = This


class IGroupRow(IRow):
    children = List(IRow)

    def add_row(self, row: IRow):
        """Routine for adding a step to this group"""

    def insert_row(self, idx, row: IRow):
        """Routine for inserting a step to this group at a specific idx"""

    def remove_row(self, row: IRow):
        """Routine for removing a step"""
