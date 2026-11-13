# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Undo/redo history for protocol tree edits (#967).

Every edit reaches the ``RowManager`` as ``rows_changed`` or ``cell_changed``
— the delegate, bulk set, paste, fill pattern and the device viewer's
write-backs alike. Rather than wrap each edit site in its own command, the
history snapshots the protocol with the persistence serializer once an edit
settles and pushes one ``ProtocolSnapshotCommand`` holding the snapshots
either side of it. Everything one user action changes before control returns
to the event loop — a bulk set over many rows, a multi-row paste, the
reconciliation a cell edit cascades into — settles into a single entry.

Undo and redo apply only the difference between a command's two snapshots,
resolved against the live tree by row uuid on every call: surviving rows keep
their objects (per-step references stay valid), cells the command did not
change keep their live values, and no trait container is ever captured
(#755). The per-protocol metadata (the device's electrode map) is not
user-edited and is left out of the snapshots.
"""

# Standard library imports.
import json

# Enthought library imports.
from pyface.undo.api import AbstractCommand, CommandStack, UndoManager
from traits.api import (
    Bool,
    Callable,
    HasTraits,
    Instance,
    Int,
    Property,
    Str,
    observe,
)

# Microdrop package imports.
from pluggable_protocol_tree.consts import PROTOCOL_HISTORY_MAX_ENTRIES
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Per-row fields the serializer writes for the row itself, not a column; they
#: identify and place the row (the name is the one editable one).
_ROW_IDENTITY_FIELDS = ("depth", "uuid", "type")


# --- snapshots ---------------------------------------------------------


def snapshot_protocol(manager):
    """Return the tree as a compact JSON string: the save format without the
    protocol metadata."""
    payload = manager.to_json()
    payload.pop("protocol_metadata", None)

    return json.dumps(payload, separators=(",", ":"))


def _rows_by_uuid(payload):
    """Map each row's uuid to its ``{field: value}`` dict, in tree order."""
    fields = payload["fields"]
    rows = {}

    for values in payload["rows"]:
        row = dict(zip(fields, values))
        rows.setdefault(row["uuid"], row)

    return rows


def _skeleton(payload):
    """The tree's shape: ``(depth, uuid, type)`` per row, in tree order."""
    return [tuple(values[:3]) for values in payload["rows"]]


def _row_flags(payload, uuid):
    return (payload.get("row_flags") or {}).get(uuid, {})


def _same_value(a, b):
    """Snapshot values are parsed JSON, so ``==`` holds except for NaN."""
    return a == b or json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --- applying a change -------------------------------------------------


def apply_protocol_change(manager, source, target):
    """Turn the live tree from snapshot ``source`` into snapshot ``target``,
    touching only what differs between the two.

    A change that keeps the tree's shape is written cell by cell, each firing
    ``cell_changed`` like an edit from the grid; one that reshapes it re-parents
    the live rows (creating those ``target`` has and the tree lost) and fires
    ``rows_changed`` once.
    """
    live_rows = {}

    for row in manager.iter_all_rows():
        live_rows.setdefault(row.uuid, row)

    source_rows = _rows_by_uuid(source)
    target_rows = _rows_by_uuid(target)
    written_cells = []

    for uuid, target_values in target_rows.items():
        live_row = live_rows.get(uuid)
        source_values = source_rows.get(uuid)

        if live_row is None or source_values is None:
            continue

        for field in _write_row_values(
            manager,
            live_row,
            source_values,
            target_values,
            _row_flags(source, uuid),
            _row_flags(target, uuid),
        ):
            written_cells.append((live_row, field))

    if _skeleton(source) != _skeleton(target):
        _rebuild_structure(manager, target, target_rows, live_rows)

        return

    for row, field in written_cells:
        manager.cell_changed = {"path": tuple(row.path), "col_id": field}


def _write_row_values(
    manager, row, source_values, target_values, source_flags, target_flags
):
    """Write the values that differ between ``source_values`` and
    ``target_values`` onto ``row``; return the fields written."""
    columns = {column.model.col_id: column for column in manager.columns}
    written = []

    for field, value in target_values.items():
        if field in _ROW_IDENTITY_FIELDS:
            continue

        if field in source_values and _same_value(source_values[field], value):
            continue

        if field == "name":
            row.name = value
            written.append(field)

            continue

        column = columns.get(field)

        if column is None:
            continue

        setattr(row, field, column.model.deserialize(value))
        written.append(field)

    duration_controls = bool(target_flags.get("repeat_duration_controls", False))
    flags_changed = duration_controls != bool(
        source_flags.get("repeat_duration_controls", False)
    )

    if flags_changed:
        row.repeat_duration_controls = duration_controls

    if written or flags_changed:
        _rebuild_runtime_state(manager, row)

    return written


def _rebuild_runtime_state(manager, row):
    """Let each column rebuild its runtime-derived row state (column locks)
    from the values just written, as a protocol load does."""
    for column in manager.columns:
        hook = getattr(column.model, "on_row_loaded", None)

        if hook is not None:
            hook(row)


def _rebuild_structure(manager, target, target_rows, live_rows):
    """Re-parent the live rows into ``target``'s shape, creating the rows the
    live tree lacks from their ``target`` values; rows ``target`` lacks are
    detached."""
    children_by_group = {id(manager.root): (manager.root, [])}
    stack = [manager.root]

    for depth, uuid, row_type in _skeleton(target):
        row = live_rows.pop(uuid, None)

        if row is None or row.row_type != row_type:
            row = _new_row(manager, target, target_rows[uuid])

        stack = stack[: depth + 1]
        children_by_group[id(stack[-1])][1].append(row)

        if row_type == "group":
            children_by_group.setdefault(id(row), (row, []))
            stack.append(row)

    old_groups = [manager.root] + [
        row for row in live_rows.values() if isinstance(row, GroupRow)
    ]

    for group in old_groups:
        group.children[:] = []

    for row in live_rows.values():
        row.parent = None

    for group, children in children_by_group.values():
        for child in children:
            child.parent = group

        group.children[:] = children

    # The tree view keeps its selection by row position; keep the selected
    # paths that still exist so the manager agrees with it.
    manager.selection = [
        path for path in manager.selection if _path_exists(manager, path)
    ]
    manager.rows_changed = True


def _path_exists(manager, path):
    try:
        manager.get_row(tuple(path))
    except (IndexError, AttributeError):
        return False

    return True


def _new_row(manager, target, values):
    """Build a row from its ``target`` snapshot values (an undone delete)."""
    row_type = manager.step_type if values["type"] == "step" else manager.group_type
    row = row_type(name=values["name"], uuid=values["uuid"])

    _write_row_values(manager, row, {}, values, {}, _row_flags(target, values["uuid"]))

    return row


# --- naming --------------------------------------------------------------


def _count_noun(count, noun):
    return noun if count == 1 else f"{count} {noun}s"


def _describe_rows(rows):
    """'Step', '3 Steps', 'Group' (a group counts with its contents)."""
    groups = sum(1 for row in rows if row["type"] == "group")

    if groups:
        return _count_noun(groups, "Group")

    return _count_noun(len(rows), "Step")


def describe_change(source, target, columns):
    """Name the edit turning snapshot ``source`` into ``target`` for the
    undo/redo tooltips: "Delete Step", "Edit Duration (s)", "Move Rows"."""
    source_rows = _rows_by_uuid(source)
    target_rows = _rows_by_uuid(target)

    added = [row for uuid, row in target_rows.items() if uuid not in source_rows]
    removed = [row for uuid, row in source_rows.items() if uuid not in target_rows]

    if added and not removed:
        return f"Add {_describe_rows(added)}"

    if removed and not added:
        return f"Delete {_describe_rows(removed)}"

    if added or removed:
        return "Edit Protocol"

    if _skeleton(source) != _skeleton(target):
        return "Move Rows"

    changed_fields = set()
    changed_rows = []

    for uuid, target_values in target_rows.items():
        source_values = source_rows[uuid]
        fields = {
            field
            for field, value in target_values.items()
            if field not in _ROW_IDENTITY_FIELDS
            and not _same_value(source_values.get(field), value)
        }

        if fields or _row_flags(source, uuid) != _row_flags(target, uuid):
            changed_fields |= fields
            changed_rows.append(target_values)

    row_noun = (
        "Group" if changed_rows and changed_rows[0]["type"] == "group" else "Step"
    )

    if changed_fields == {"name"}:
        return f"Rename {row_noun}" if len(changed_rows) == 1 else "Rename Rows"

    if len(changed_fields) == 1:
        col_names = {column.model.col_id: column.model.col_name for column in columns}
        field = next(iter(changed_fields))

        return f"Edit {col_names.get(field, field)}"

    if len(changed_rows) == 1:
        return f"Edit {row_noun}"

    return "Edit Cells"


# --- commands and history --------------------------------------------------


class ProtocolSnapshotCommand(AbstractCommand):
    """One settled protocol edit, held as the snapshots either side of it.

    Pushed after the edit was applied, so ``do`` is a no-op.
    """

    name = Str("Edit Protocol")

    #: The edited protocol — the owner, whose tree is resolved live on every
    #: undo/redo; never one of its containers (#755).
    manager = Instance(RowManager)

    #: ``snapshot_protocol`` output before and after the edit.
    before = Str()
    after = Str()

    def do(self):
        pass

    def undo(self):
        apply_protocol_change(
            self.manager, json.loads(self.after), json.loads(self.before)
        )

    def redo(self):
        apply_protocol_change(
            self.manager, json.loads(self.before), json.loads(self.after)
        )


class BoundedCommandStack(CommandStack):
    """A ``CommandStack`` that forgets its oldest entries beyond ``max_entries``."""

    max_entries = Int(PROTOCOL_HISTORY_MAX_ENTRIES)

    def push(self, command):
        result = super().push(command)
        excess = len(self._stack) - self.max_entries

        if excess > 0:
            del self._stack[:excess]
            self._index -= excess
            self.undo_manager.stack_updated = self

        return result


class ProtocolHistory(HasTraits):
    """Record protocol edits as they settle and undo/redo them.

    Nothing is recorded, undone or redone while a run is active: edits a run
    makes (Advanced Mode edits, playback write-backs) stay out of the history,
    which rebases on whatever the run left once it ends.
    """

    #: The protocol whose edits are recorded.
    manager = Instance(RowManager)

    #: Run state (``is_active``); None in headless use, where nothing runs.
    protocol_state_tracker = Instance(PluggableProtocolStateTracker)

    #: Holds one ``ProtocolSnapshotCommand`` per settled edit.
    undo_manager = Instance(UndoManager)

    #: Edits kept before the oldest are forgotten.
    max_entries = Int(PROTOCOL_HISTORY_MAX_ENTRIES)

    #: Called with ``flush`` to run it once the current action has finished
    #: editing (the app passes ``GUI.invoke_later``). None flushes on every
    #: edit event, so a multi-row action records one entry per event.
    schedule_flush = Callable()

    #: Name of the edit Undo would revert ("" when there is none).
    undo_name = Property(Str, observe="undo_manager.stack_updated")

    #: Name of the edit Redo would re-apply ("" when there is none).
    redo_name = Property(Str, observe="undo_manager.stack_updated")

    #: The protocol as of the last recorded edit, undo or reset.
    _snapshot = Str()

    #: True from an edit event until the flush that records it.
    _pending = Bool(False)

    #: Name of the open ``RowManager.named_edit`` action, if any.
    _pending_name = Str()

    #: Nesting depth of open ``named_edit`` actions; edits made inside one
    #: are recorded together when the outermost closes.
    _action_depth = Int(0)

    #: True while an undo/redo writes the tree, so its events are not edits.
    _restoring = Bool(False)

    def _undo_manager_default(self):
        stack = BoundedCommandStack(max_entries=self.max_entries)
        undo_manager = UndoManager(active_stack=stack)
        stack.undo_manager = undo_manager

        return undo_manager

    def traits_init(self):
        self._snapshot = snapshot_protocol(self.manager)

    def _get_undo_name(self):
        return self.undo_manager.undo_name

    def _get_redo_name(self):
        return self.undo_manager.redo_name

    # --- recording ---

    def _is_running(self):
        tracker = self.protocol_state_tracker

        return tracker is not None and tracker.is_active

    @observe("manager:rows_changed, manager:cell_changed")
    def _on_protocol_edited(self, event):
        if self._restoring or self._is_running():
            return

        self._mark_pending()

    @observe("manager:edit_action")
    def _on_edit_action(self, event):
        if self._restoring or self._is_running():
            return

        if event.new:
            # Settle what came before, so the action's entry holds only its
            # own edits.
            if self._action_depth == 0:
                self.flush()
                self._pending_name = event.new

            self._action_depth += 1

            return

        self._action_depth = max(0, self._action_depth - 1)

        if self._action_depth == 0:
            self.flush()

    def _mark_pending(self):
        if self._pending:
            return

        self._pending = True

        if self.schedule_flush is None:
            self.flush()
        else:
            self.schedule_flush(self.flush)

    def flush(self):
        """Record the edits made since the last flush as one history entry.

        Deferred while a ``named_edit`` action is open: a modal prompt inside
        the action runs the event loop, and with it a scheduled flush.
        """

        if self._action_depth:
            return

        name = self._pending_name
        self._pending_name = ""

        if not self._pending:
            return

        self._pending = False

        try:
            snapshot = snapshot_protocol(self.manager)
        except (TypeError, ValueError):
            logger.exception("Protocol edit not recorded: the tree did not serialize")

            return

        if snapshot == self._snapshot:
            return

        before = self._snapshot
        self._snapshot = snapshot

        if not name:
            name = describe_change(
                json.loads(before), json.loads(snapshot), self.manager.columns
            )

        logger.debug(f"Protocol history: recorded '{name}'")
        self.undo_manager.active_stack.push(
            ProtocolSnapshotCommand(
                name=name, manager=self.manager, before=before, after=snapshot
            )
        )

    @observe("protocol_state_tracker:is_active")
    def _on_run_state_changed(self, event):
        if event.new:
            self.flush()

            return

        self._pending = False
        self._pending_name = ""
        self._action_depth = 0
        self._snapshot = snapshot_protocol(self.manager)

    # --- undo / redo ---

    def undo(self):
        """Revert the newest recorded edit; ignored during a run."""

        if self._is_running():
            return

        self.flush()
        self._restore(self.undo_manager.undo)

    def redo(self):
        """Re-apply the newest undone edit; ignored during a run."""

        if self._is_running():
            return

        self.flush()
        self._restore(self.undo_manager.redo)

    def _restore(self, step):
        self._restoring = True

        try:
            step()
        finally:
            self._restoring = False
            self._snapshot = snapshot_protocol(self.manager)

    def reset(self):
        """Forget every entry and rebase on the current protocol (New, Open,
        a column-set change)."""
        self._pending = False
        self._pending_name = ""
        self._action_depth = 0
        self._snapshot = snapshot_protocol(self.manager)
        self.undo_manager.active_stack.clear()
