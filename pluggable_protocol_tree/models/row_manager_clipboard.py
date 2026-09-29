# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Clipboard for ``RowManager`` (issue #641 step 3): the payload-layer
serialize/reconstruct helpers plus the public copy/cut/paste API that
wraps the system QClipboard.

``RowManagerClipboardMixin`` is mixed into ``RowManager`` by plain multiple
inheritance for the same reason ``RowManagerPersistenceMixin`` is (see that
module's docstring): ``copy``/``cut``/``paste`` are RowManager's own public
API, and a mixin keeps every external call site (``manager.copy()``, the
tree widget's Ctrl+C/X/V handlers) unchanged.
"""

# Standard library imports.
from typing import Optional, Tuple

# Microdrop package imports.
from pluggable_protocol_tree.models.row import BaseRow, GroupRow

Path = Tuple[int, ...]


class RowManagerClipboardMixin:
    """``copy`` / ``cut`` / ``paste`` and their payload-layer helpers, mixed
    into ``RowManager``. Depends only on the host's public+protected API
    (``root``, ``columns``, ``selection``, ``step_type``, ``group_type``,
    ``rows_changed``, ``get_row``, ``remove``, ``_is_ancestor``) — no state
    of its own.
    """

    # --- clipboard (payload-layer; QClipboard IO lives in copy/cut/paste) ---

    def _field_index(self, col_id: str) -> int:
        """Position of col_id in the serialized row tuple (depth/uuid/type/name
        come first, then columns in their self.columns order)."""
        fields = ["depth", "uuid", "type", "name"] + [
            c.model.col_id for c in self.columns
        ]

        return fields.index(col_id)

    def _serialize_selection(self) -> dict:
        """Return a clipboard-style payload covering the current selection.

        Format mirrors persistence (no schema_version on the clipboard):
        {"columns": [...], "fields": [...],
         "rows": [[depth, uuid, type, name, *values], ...]}
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
            if any(
                self._is_ancestor(tuple(other), tuple(p))
                for other in self.selection
                if other != p
            ):
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
        col_ids_in_payload: list = fields[4:]  # skip depth, uuid, type, name
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
        stack: list = [target_parent]  # stack[-1] is the current parent
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
                    continue  # orphan column (PPT-1 scope: skip silently)
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
        import json

        from pyface.qt.QtWidgets import QApplication

        payload = self._serialize_selection()
        mime_text = json.dumps(payload)
        cb = QApplication.clipboard()
        cb.setText(mime_text)  # TODO(PPT-1): use MIME-typed QMimeData for xplat
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
