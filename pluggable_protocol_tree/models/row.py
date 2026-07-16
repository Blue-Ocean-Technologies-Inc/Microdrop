"""Row models for the protocol tree.

BaseRow is the leaf type (steps). GroupRow nests other rows as children.
Path is derived from parent chain + sibling position; it's not stored, so
mutations to the tree automatically invalidate and recompute it via the
Property observe dependency list.

Dynamic per-protocol subclasses (see `build_row_type`) inherit from these
and add one trait per column in the active column set.
"""

import uuid as _uuid

from traits.api import (
    HasTraits, Str, List, Instance, Tuple, Property, Bool, Dict, provides,
    observe,
)

from pluggable_protocol_tree.interfaces.i_row import IRow, IGroupRow


@provides(IRow)
class BaseRow(HasTraits):
    uuid = Str(desc="Stable identity for merges/diffs and device-viewer routing")
    name = Str("Step", desc="User-visible row name")
    parent = Instance("BaseRow", desc="Owning GroupRow (None for rows at the top)")
    row_type = Str("step", desc="'step' or 'group' — drives per-column visibility")
    path = Property(Tuple, observe="parent.path, parent.children.items",
                    desc="0-indexed tuple of positions from the root (empty for orphans)")
    repeat_duration_controls = Bool(
        False,
        desc="Internal mode flag: True when Route Reps Dur is the "
             "authoritative loop knob; False when Route Reps controls. "
             "Not a column — persisted via the row_flags map.")
    column_locks = Dict(
        Str, Dict,
        desc="Owner-keyed per-row column locks: {col_id: {owner: reason}}. "
             "Runtime-derived state, rebuilt from its source on load — "
             "never persisted (a lock with no live owner could never be "
             "released).")

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

    def dotted_path(self) -> str:
        """1-indexed dotted display id ('1.2.3') for this row — matches
        the Id column's rendering. Empty string for detached rows."""
        return ".".join(str(i + 1) for i in self.path) if self.path else ""

    # --- per-row column locks (issue #541) ---

    def lock_column(self, col_id: str, owner: str, reason: str = "") -> None:
        """Lock ``col_id``'s cell on this row on behalf of ``owner``.

        ``reason`` surfaces as the cell tooltip. The whole dict is
        rebuilt and reassigned so trait observers (the tree model's
        repaint wiring) fire — Traits does not notify on nested
        mutation.
        """
        locks = {cid: dict(owners) for cid, owners in self.column_locks.items()}
        locks.setdefault(col_id, {})[owner] = reason
        self.column_locks = locks

    def unlock_column(self, col_id: str, owner: str) -> None:
        """Release ``owner``'s lock on ``col_id``. The cell stays locked
        while any other owner still holds one. Unknown column ids or
        owners are a no-op."""
        if owner not in self.column_locks.get(col_id, {}):
            return
        locks = {cid: dict(owners) for cid, owners in self.column_locks.items()}
        del locks[col_id][owner]
        if not locks[col_id]:
            del locks[col_id]
        self.column_locks = locks

    def is_column_locked(self, col_id: str) -> bool:
        return bool(self.column_locks.get(col_id))

    def column_lock_reasons(self, col_id: str) -> list:
        """Non-empty lock reasons for ``col_id`` — the cell tooltip."""
        return [reason for reason in self.column_locks.get(col_id, {}).values()
                if reason]

    @observe("repeat_duration_controls")
    def _sync_repeat_duration_lock(self, event):
        # "Route Reps will become read-only while Route Reps Dur is in
        # control" — the mode-handoff dialog's promise (issue #541
        # debt). Observed on the trait, not done in the column handler,
        # because DV-sidebar sync and protocol load write this flag
        # directly and the lock must follow on every path.
        if event.new:
            self.lock_column("route_repetitions", owner="repeat_duration",
                             reason="Route Reps Dur is in control")
        else:
            self.unlock_column("route_repetitions", owner="repeat_duration")


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


def build_row_type(columns, base=BaseRow, name="ProtocolStepRow") -> type:
    """Build a fresh HasTraits subclass of `base` with one trait per column.

    Called once per protocol open (twice actually: for step and group
    subclasses). The subclass is per-protocol-session; closing a protocol
    lets Python garbage-collect it. This avoids mutating shared classes,
    preserves full Traits semantics (observers, validation, defaults),
    and keeps the row schema explicit.

    Args:
        columns: List of IColumn instances contributing traits.
        base: BaseRow (for steps) or GroupRow (for groups).
        name: Name for the new class (shown in tracebacks only).

    Returns:
        A new class derived from `base` with each column's trait added.
    """
    class_dict = {
        col.model.col_id: col.model.trait_for_row()
        for col in columns
    }
    return type(name, (base,), class_dict)
