"""Traits interfaces for protocol rows (steps and groups).

BaseRow instances are the leaves of the protocol tree. GroupRow instances
own ordered children. Dynamic subclasses composed from the active column
set hold the per-column trait values — see models/row.py::build_row_type.
"""

from traits.api import Interface, Str, List, Instance, Tuple


class IRow(Interface):
    """A single row in the protocol tree.

    Invariants:
    - `uuid` is stable for the lifetime of the row and survives save/load.
      A fresh uuid is generated on copy/paste.
    - `parent` is None only for rows owned directly by the RowManager.root.
    - `path` is a tuple of 0-indexed positions from the root; derived, not
      stored. Display elsewhere is 1-indexed.
    """
    uuid = Str
    name = Str
    parent = Instance("IRow")
    row_type = Str  # "step" or "group"
    path = Tuple


class IGroupRow(IRow):
    """A row that owns ordered children (other rows or nested groups)."""
    children = List(Instance(IRow))

    def add_row(self, row):
        """Append a row to children; set its parent to self."""

    def insert_row(self, idx, row):
        """Insert a row at idx in children; set its parent to self."""

    def remove_row(self, row):
        """Remove a row from children; clear its parent."""
