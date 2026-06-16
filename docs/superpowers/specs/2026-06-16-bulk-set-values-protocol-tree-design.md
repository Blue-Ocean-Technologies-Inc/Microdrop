# Bulk Set Values for the pluggable protocol tree (#474)

Mirror of legacy `protocol_grid` issues #167 ("Apply parameter to multiple
steps in bulk") and #285 ("Checkbox to apply new bulk parameters to all nested
groups"), rebuilt on the new tree's data model.

## Goal

Let the user set one or more column values across all currently-selected steps
in a single action. When a **group** is selected, by default only its
first-level child steps are affected; an "Apply to all nested groups" checkbox
extends the write to every descendant step.

## Why it's small on the new model

The `RowManager` already provides the write primitive:

- `set_values(paths, col_id, value)` — writes `value` to `col_id` on each path
  and fires `cell_changed` per row, so the protocol state tracker's dirty
  bookkeeping, the Route-Reps-Dur reconciliation, and the device-viewer sync
  all run exactly as they do for a manual cell edit.
- `step_type()` — builds a fresh default step row (the dialog's template).
- `_walk()` / `GroupRow.children` — group traversal.

There is **no undo stack** in this tree (unlike the device viewer), so the apply
path needs nothing beyond `set_values`.

## Components

### 1. Trigger — `ProtocolTreeWidget._on_context_menu`

Add a **"Bulk Set Values…"** action to the existing right-click menu, beside
Copy / Cut / Paste / Delete. It calls `_bulk_set_values()`. With no rows
selected it is a no-op (the dialog never opens).

### 2. `RowManager.steps_under(paths, recursive=False) -> list[Path]`

Resolves a selection into the **step** paths to write to:

- A selected step (`not isinstance(row, GroupRow)`) contributes its own path.
- A selected group contributes its **direct child steps**, or **all descendant
  steps** when `recursive` is true (groups themselves are never written to).
- Result is de-duplicated (a step that is both directly selected and under a
  selected group appears once) and order-preserving.

Lives on `RowManager` because it derives target rows from the tree structure.
Pure model logic — unit-testable headless.

### 3. `BulkSetDialog(QDialog)` — new `views/bulk_set_dialog.py`

Built around a throwaway **template step row** = `manager.step_type()`.

- **Settable columns** = columns whose view, evaluated against the template
  step, is editable or user-checkable: `get_flags(template) & ItemIsEditable`
  or `& ItemIsUserCheckable`. Read-only columns (type, id, derived cells) and
  group-only columns are excluded automatically.
- One grid row per settable column: `[☐ Apply] [col_name] [value widget]`.
  - Value widget for editable columns: `col.view.create_editor(self, template)`
    (the column's own line-edit / spinbox / combobox), seeded via
    `set_editor_data(editor, default)` where `default = col.model.get_value(template)`.
  - Value widget for checkbox columns (`create_editor` returns `None`, view is
    checkable): a `QCheckBox`.
  - The value widget is disabled until its **Apply** box is ticked.
- Bottom: **`[☐ Apply to all nested groups]`** then `[Cancel] [OK]`.
- API:
  - `values() -> dict[str, Any]` — `{col_id: value}` for ticked rows only;
    editable values via `col.view.get_editor_data(editor)`, checkbox values via
    `QCheckBox.isChecked()`.
  - `apply_nested -> bool` — the nested-groups checkbox state.

The template row makes this elegant: the dialog reuses each column's real editor
widget and value plumbing instead of re-deriving per-type widgets, and the row
serves as the `create_editor` context for row-dependent bounds (e.g. trail
overlay ≤ trail length − 1 reads the template's trail length).

### 4. Apply — `ProtocolTreeWidget._bulk_set_values()`

1. `paths = [self._index_to_path(i) for i in self.tree.selectionModel().selectedRows(0)]`
   (same source `_paste` uses).
2. If `paths` is empty, return.
3. `dialog = BulkSetDialog(self._manager, parent=self)`; if `dialog.exec()` is
   not Accepted, return.
4. `targets = self._manager.steps_under(paths, recursive=dialog.apply_nested)`.
5. For each `col_id, value` in `dialog.values().items()`:
   `self._manager.set_values(targets, col_id, value)`.

## Data flow

```
right-click → "Bulk Set Values…"
  → selectedRows → paths
  → BulkSetDialog(manager) → {col_id: value}, apply_nested
  → manager.steps_under(paths, recursive=apply_nested) → step paths
  → manager.set_values(paths, col_id, value)  [per column]
      → cell_changed per (path, col_id)
          → protocol_state_tracker (dirty) + Route-Reps-Dur reconcile + DV sync
```

## Error handling

- Empty selection: no dialog, no-op.
- Selection containing only groups with no descendant steps: `steps_under`
  returns `[]`; `set_values([])` is a harmless no-op.
- Stale paths are not a concern — the dialog is modal, so the tree can't mutate
  between selection capture and apply.

## Scope / YAGNI

- Targets are always **steps**; groups are only ever expanded, never written
  to, so no per-row "is this column valid for a group" check is needed.
- Compound columns whose view exposes no single value widget (`create_editor`
  is `None` and the view is not checkable) are simply not listed as settable in
  v1. Per-field bulk-set for compounds can follow later if needed.
- No undo integration (the tree has no undo stack).

## Testing

- `RowManager.steps_under` (headless): single step; a group → direct children
  only; a group with `recursive=True` → all descendants; dedup when a step is
  both directly selected and under a selected group; group with no steps → `[]`.
- `BulkSetDialog` (with `qapp`): `values()` returns only ticked columns with the
  edited values; unticked columns are absent; `apply_nested` reflects the
  checkbox.

## Files

- New: `pluggable_protocol_tree/views/bulk_set_dialog.py`
- Edit: `pluggable_protocol_tree/views/tree_widget.py` (menu item + `_bulk_set_values`)
- Edit: `pluggable_protocol_tree/models/row_manager.py` (`steps_under`)
- Tests: `tests/test_row_manager.py` (or a new `test_bulk_set.py`) + a dialog test.
