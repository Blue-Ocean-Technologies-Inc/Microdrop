"""Central manager for the protocol tree — structure, selection, clipboard,
slicing, iteration, persistence.

Selection is stored as a list of 0-indexed path tuples, not row refs: paths
survive tree mutations during paste, but row references don't. The
dynamic step/group subclasses are built once at construction from the
active column set.
"""

from typing import Iterator, List, Optional, Tuple

from traits.api import (
    HasTraits, Instance, List as ListTrait, Tuple as TupleTrait, Int,
    Event, Str, observe,
)

from pluggable_protocol_tree.consts import PROTOCOL_ROWS_MIME
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models.row import BaseRow, GroupRow, build_row_type


Path = Tuple[int, ...]


class RowManager(HasTraits):
    """Single public API for every tree operation."""

    root = Instance(GroupRow)
    columns = ListTrait(Instance(IColumn))

    step_type = Instance(type)
    group_type = Instance(type)

    selection = ListTrait(TupleTrait(Int),
        desc="List of 0-indexed path tuples currently selected")

    clipboard_mime = Str(PROTOCOL_ROWS_MIME)

    rows_changed = Event(
        desc="Fires on structure or value changes. Batch-coalesced by UI.")

    # --- construction ---

    def traits_init(self):
        if self.root is None:
            self.root = GroupRow(name="Root")
        self._rebuild_types()

    @observe("columns.items")
    def _on_columns_change(self, event):
        self._rebuild_types()

    def _rebuild_types(self):
        self.step_type = build_row_type(
            self.columns, base=BaseRow, name="ProtocolStepRow",
        )
        self.group_type = build_row_type(
            self.columns, base=GroupRow, name="ProtocolGroupRow",
        )

    # --- tree lookup ---

    def get_row(self, path: Path) -> BaseRow:
        """Navigate to the row at `path`. Raises IndexError if invalid."""
        current = self.root
        for idx in path:
            current = current.children[idx]
        return current

    def _parent_for_path(self, parent_path: Path) -> GroupRow:
        target = self.root if parent_path == () else self.get_row(parent_path)
        if not isinstance(target, GroupRow):
            raise ValueError(f"Path {parent_path} is not a group")
        return target

    # --- structure mutation ---

    def add_step(self, parent_path: Path = (), index: Optional[int] = None,
                 values: Optional[dict] = None) -> Path:
        parent = self._parent_for_path(parent_path)
        row = self.step_type()
        if values:
            for k, v in values.items():
                setattr(row, k, v)
        if index is None:
            index = len(parent.children)
        parent.insert_row(index, row)
        self.rows_changed = True
        return parent_path + (index,)

    def add_group(self, parent_path: Path = (), index: Optional[int] = None,
                  name: str = "Group") -> Path:
        parent = self._parent_for_path(parent_path)
        row = self.group_type(name=name)
        if index is None:
            index = len(parent.children)
        parent.insert_row(index, row)
        self.rows_changed = True
        return parent_path + (index,)

    def remove(self, paths: List[Path]) -> None:
        """Remove all rows at `paths`. Paths that refer to a descendant of
        another removed path are skipped (the ancestor removal already
        takes them out)."""
        paths = [tuple(p) for p in paths]
        # Sort reverse-lexicographically so deeper removes don't shift
        # the indices of later ones.
        paths_sorted = sorted(paths, reverse=True)
        seen_ancestors: List[Path] = []
        for p in paths_sorted:
            if any(self._is_ancestor(a, p) for a in seen_ancestors):
                continue
            seen_ancestors.append(p)
            row = self.get_row(p)
            parent = row.parent
            if parent is not None:
                parent.remove_row(row)
        self.rows_changed = True

    @staticmethod
    def _is_ancestor(ancestor: Path, descendant: Path) -> bool:
        return (len(ancestor) < len(descendant)
                and descendant[: len(ancestor)] == ancestor)

    def move(self, paths: List[Path], target_parent_path: Path,
             target_index: int) -> None:
        """Move rows to a new parent. Collects rows first (while paths are
        still valid), then inserts at the target, removing from the old
        location afterwards."""
        rows = [self.get_row(tuple(p)) for p in paths]
        target = self._parent_for_path(target_parent_path)
        # Remove from old parents (in reverse order of the old paths so
        # indices don't shift).
        for row in rows:
            if row.parent is not None:
                row.parent.remove_row(row)
        for offset, row in enumerate(rows):
            target.insert_row(target_index + offset, row)
        self.rows_changed = True

    # --- selection ---

    def select(self, paths: List[Path], mode: str = "set") -> None:
        """Update `selection`.

        Modes:
        - 'set'   : replace selection with `paths`
        - 'add'   : append `paths`, deduplicating
        - 'range' : selection becomes all top-level siblings between the
                    first and last of `paths`. Only meaningful when the
                    given paths have a common parent.
        """
        paths = [tuple(p) for p in paths]
        if mode == "set":
            self.selection = paths
        elif mode == "add":
            seen = set(tuple(p) for p in self.selection)
            new = [p for p in paths if p not in seen]
            self.selection = list(self.selection) + new
        elif mode == "range":
            if not paths:
                return
            # Take common parent of first and last; select siblings
            # between their positions.
            first, last = paths[0], paths[-1]
            if first[:-1] != last[:-1]:
                # Different parents — fall back to 'set'.
                self.selection = [first, last]
                return
            parent_path = first[:-1]
            lo, hi = sorted([first[-1], last[-1]])
            self.selection = [parent_path + (i,) for i in range(lo, hi + 1)]
        else:
            raise ValueError(f"Unknown selection mode: {mode}")

    def selected_rows(self) -> List[BaseRow]:
        return [self.get_row(p) for p in self.selection]

    # --- uuid lookup ---

    def get_row_by_uuid(self, uuid: str) -> Optional[BaseRow]:
        return self._find_by_uuid(self.root, uuid)

    @classmethod
    def _find_by_uuid(cls, node, uuid: str) -> Optional[BaseRow]:
        if isinstance(node, GroupRow):
            for child in node.children:
                if child.uuid == uuid:
                    return child
                found = cls._find_by_uuid(child, uuid)
                if found is not None:
                    return found
        return None
