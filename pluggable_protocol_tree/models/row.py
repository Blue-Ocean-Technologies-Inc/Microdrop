"""Row models for the protocol tree.

BaseRow is the leaf type (steps). GroupRow nests other rows as children.
Path is derived from parent chain + sibling position; it's not stored, so
mutations to the tree automatically invalidate and recompute it via the
Property observe dependency list.

Dynamic per-protocol subclasses (see `build_row_type`) inherit from these
and add one trait per column in the active column set.
"""

import uuid as _uuid

from traits.api import HasTraits, Str, List, Instance, Tuple, Property, provides

from pluggable_protocol_tree.interfaces.i_row import IRow, IGroupRow


@provides(IRow)
class BaseRow(HasTraits):
    uuid = Str(desc="Stable identity for merges/diffs and device-viewer routing")
    name = Str("Step", desc="User-visible row name")
    parent = Instance("BaseRow", desc="Owning GroupRow (None for rows at the top)")
    row_type = Str("step", desc="'step' or 'group' — drives per-column visibility")
    path = Property(Tuple, observe="parent.path, parent.children.items",
                    desc="0-indexed tuple of positions from the root (empty for orphans)")

    def _uuid_default(self):
        return _uuid.uuid4().hex

    def _get_path(self):
        indices: list[int] = []
        current = self
        while current.parent is not None:
            try:
                idx = current.parent.children.index(current)
            except ValueError:
                return ()   # row was detached mid-read; report empty
            indices.insert(0, idx)
            current = current.parent
        return tuple(indices)


@provides(IGroupRow)
class GroupRow(BaseRow):
    children = List(Instance(BaseRow))

    def _row_type_default(self):
        return "group"

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
