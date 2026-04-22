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

    # --- clipboard (payload-layer; QClipboard IO lives in copy/cut/paste) ---

    def _field_index(self, col_id: str) -> int:
        """Position of col_id in the serialized row tuple (depth/uuid/type/name
        come first, then columns in their self.columns order)."""
        fields = ["depth", "uuid", "type", "name"] + [c.model.col_id for c in self.columns]
        return fields.index(col_id)

    def _serialize_selection(self) -> dict:
        """Return a clipboard-style payload covering the current selection.

        Format mirrors persistence (no schema_version on the clipboard):
        {"columns": [...], "fields": [...], "rows": [[depth, uuid, type, name, *values], ...]}
        Children of a selected group are included automatically.
        """
        rows_out: list = []
        field_names = ["depth", "uuid", "type", "name"] + [
            c.model.col_id for c in self.columns
        ]

        def emit(row: BaseRow, depth: int):
            vals = [depth, row.uuid, row.row_type, row.name]
            for col in self.columns:
                raw = col.model.get_value(row)
                vals.append(col.model.serialize(raw))
            rows_out.append(vals)
            if isinstance(row, GroupRow):
                for child in row.children:
                    emit(child, depth + 1)

        # Emit top-level selected rows; children handled recursively.
        for p in self.selection:
            row = self.get_row(p)
            # Skip rows whose ancestor is also selected (covered already).
            if any(self._is_ancestor(tuple(other), tuple(p))
                   for other in self.selection if other != p):
                continue
            emit(row, depth=0)

        return {
            "columns": [
                {
                    "id": c.model.col_id,
                    "cls": f"{type(c.model).__module__}.{type(c.model).__name__}",
                }
                for c in self.columns
            ],
            "fields": field_names,
            "rows": rows_out,
        }

    def _paste_from_payload(self, payload: dict, target_path: Optional[Path]) -> None:
        """Reconstruct rows from `payload` and insert after `target_path`
        (or at the end of root if None). Each pasted row gets a fresh uuid."""
        import uuid as _uuid

        fields: list = payload["fields"]
        col_ids_in_payload: list = fields[4:]   # skip depth, uuid, type, name
        live_by_col_id = {c.model.col_id: c for c in self.columns}

        # Determine insertion target.
        if target_path is None or target_path == ():
            target_parent = self.root
            insert_idx = len(self.root.children)
        else:
            target_row = self.get_row(target_path)
            if isinstance(target_row, GroupRow):
                target_parent = target_row
                insert_idx = len(target_row.children)
            else:
                target_parent = target_row.parent or self.root
                insert_idx = target_parent.children.index(target_row) + 1

        # Reconstruct, honoring depth stacking.
        stack: list = [target_parent]   # stack[-1] is the current parent
        base_depth = 0
        first = True
        for row_tuple in payload["rows"]:
            depth = row_tuple[0]
            row_type = row_tuple[2]
            row_name = row_tuple[3]
            values = row_tuple[4:]

            if first:
                base_depth = depth
                first = False

            relative_depth = depth - base_depth
            # Trim stack to relative_depth + 1 entries (we're a child of
            # stack[relative_depth]).
            stack = stack[: relative_depth + 1]
            parent = stack[-1]

            row_cls = self.step_type if row_type == "step" else self.group_type
            row = row_cls(name=row_name, uuid=_uuid.uuid4().hex)
            for col_id, raw in zip(col_ids_in_payload, values):
                col = live_by_col_id.get(col_id)
                if col is None:
                    continue   # orphan column (PPT-1 scope: skip silently)
                setattr(row, col_id, col.model.deserialize(raw))

            # Insert either at the computed position (top-level) or
            # just append for nested.
            if relative_depth == 0:
                parent.insert_row(insert_idx, row)
                insert_idx += 1
            else:
                parent.add_row(row)

            if row_type == "group":
                stack.append(row)

        self.rows_changed = True

    # --- public clipboard API (wraps QClipboard) ---

    def copy(self) -> None:
        """Serialize the current selection onto the system QClipboard."""
        from pyface.qt.QtWidgets import QApplication
        import json
        payload = self._serialize_selection()
        mime_text = json.dumps(payload)
        cb = QApplication.clipboard()
        cb.setText(mime_text)   # TODO(PPT-1): use MIME-typed QMimeData for xplat
        # NOTE: PPT-1 uses plain-text clipboard for simplicity; upgrading to
        # a proper application/x-microdrop-rows+json MIME type via QMimeData
        # lands when we also need cross-app paste. For within-app round-trip
        # the plain-text path is sufficient.

    def cut(self) -> None:
        self.copy()
        self.remove(list(self.selection))

    def paste(self, target_path: Optional[Path] = None) -> None:
        import json
        from pyface.qt.QtWidgets import QApplication
        cb = QApplication.clipboard()
        text = cb.text()
        if not text:
            return
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            return
        if "rows" not in payload:
            return
        self._paste_from_payload(payload, target_path)

    # --- execution iteration ---

    def iter_execution_steps(self) -> Iterator[BaseRow]:
        """Yield rows in execution order, flattening groups and expanding
        repetitions.

        Repetitions contract: any row may have an integer attribute named
        ``repetitions``. When present, that row's yield is multiplied. If
        the row is a step, it's yielded `n` times. If a group, its entire
        child-subtree is expanded n times. Missing attribute defaults to
        1 rep. (The repetitions column is a core built-in that lands
        alongside PPT-3's trail-config columns; PPT-1 establishes the
        contract so the executor in PPT-2 can rely on it.)
        """
        yield from self._expand(self.root)

    @classmethod
    def _expand(cls, node) -> Iterator[BaseRow]:
        reps = max(1, int(getattr(node, "repetitions", 1) or 1))
        if isinstance(node, GroupRow):
            for _ in range(reps):
                for child in node.children:
                    yield from cls._expand(child)
        else:
            for _ in range(reps):
                yield node

    # --- slicing (pandas facade) ---

    @property
    def table(self):
        """Snapshot DataFrame. Index = path tuples. Columns = col_ids.
        Rebuilt on each access (O(N rows)); not cached."""
        import pandas as pd
        rows_data = []
        index = []
        for path, row in self._walk():
            index.append(path)
            row_vals = {}
            for col in self.columns:
                row_vals[col.model.col_id] = col.model.get_value(row)
            rows_data.append(row_vals)
        col_ids = [c.model.col_id for c in self.columns]
        return pd.DataFrame(rows_data, index=pd.Index(index, tupleize_cols=False),
                            columns=col_ids)

    def _walk(self, node=None, prefix=()):
        """Depth-first traversal yielding (path, row). Skips the root."""
        if node is None:
            for i, child in enumerate(self.root.children):
                yield from self._walk(child, (i,))
            return
        yield (prefix, node)
        if isinstance(node, GroupRow):
            for i, child in enumerate(node.children):
                yield from self._walk(child, prefix + (i,))

    def rows(self, selector):
        df = self.table
        if isinstance(selector, slice):
            return df.iloc[selector]
        if callable(selector):
            mask = df.apply(selector, axis=1)
            return df[mask]
        if isinstance(selector, list):
            # selector is a list of path tuples
            return df.loc[[tuple(p) for p in selector]]
        raise TypeError(f"Unsupported selector type: {type(selector)}")

    def cols(self, col_ids):
        return self.table[list(col_ids)]

    def slice(self, rows=None, cols=None):
        df = self.table
        if rows is not None:
            df = self.rows(rows) if not isinstance(rows, slice) else df.iloc[rows]
        if cols is not None:
            df = df[list(cols)]
        return df

    # --- imperative bulk write ---

    def set_value(self, path: Path, col_id: str, value) -> None:
        col = self._column_by_id(col_id)
        row = self.get_row(path)
        col.model.set_value(row, value)
        self.rows_changed = True

    def set_values(self, paths: List[Path], col_id: str, value) -> None:
        col = self._column_by_id(col_id)
        for p in paths:
            col.model.set_value(self.get_row(p), value)
        self.rows_changed = True

    def apply(self, paths: List[Path], fn) -> None:
        for p in paths:
            fn(self.get_row(p))
        self.rows_changed = True

    def _column_by_id(self, col_id: str) -> IColumn:
        for c in self.columns:
            if c.model.col_id == col_id:
                return c
        raise KeyError(col_id)

    # --- persistence ---

    def to_json(self) -> dict:
        from pluggable_protocol_tree.services.persistence import serialize_tree
        return serialize_tree(self.root, list(self.columns))
