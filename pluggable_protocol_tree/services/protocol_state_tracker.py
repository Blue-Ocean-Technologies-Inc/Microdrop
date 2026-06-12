"""Tracks current protocol file state and dirty bookkeeping.

Owned by ``ProtocolTreePane``. Observers on ``protocol_name`` and
``is_modified`` rewrite ``self.dock_pane.name`` so the title reflects
the loaded file and unsaved-changes state.

Dirty model is incremental against a baseline DataFrame snapshot:

  * ``reseed_baseline(manager)`` — called on save/load/new — copies
    ``manager.table`` and clears all per-cell + structure diff state.
  * ``on_cell_changed(path, col_id, manager)`` — O(1) incremental
    update; adds to or removes from a ``dirty_cells`` set depending on
    whether the new value matches the baseline.
  * ``on_structure_changed(manager)`` — O(N) walk that compares the
    current path set against the baseline; if paths now match
    (insert+delete or move+undo), it does a full rescan to reset
    ``dirty_cells`` correctly (since cell_changed didn't see moves).

``is_modified`` is therefore "we have at least one cell that differs
from baseline OR the structure differs" — reverting a cell to its
saved value, or undoing an insert/delete, naturally clears it.

The pane wires the ``dock_pane`` reference when the dock pane mounts;
in headless tests it stays ``None`` and the observers are no-ops.
"""

import math
from pathlib import Path

import pandas as pd
from traits.api import Any, Bool, File, HasTraits, Instance, Str, observe

from logger.logger_service import get_logger
from pluggable_protocol_tree.consts import PKG_name

logger = get_logger(__name__)


def _values_equal(a, b) -> bool:
    """Cell-value equality that handles list / dict (Python ==) and NaN.

    ``nan == nan`` is False by IEEE rule but for dirty-tracking we want
    them equal (both "missing"). Lists and dicts compare with normal
    Python equality, which is what we want for routes/electrodes.
    """
    a_is_nan = isinstance(a, float) and math.isnan(a)
    b_is_nan = isinstance(b, float) and math.isnan(b)
    if a_is_nan or b_is_nan:
        return a_is_nan and b_is_nan
    try:
        return bool(a == b)
    except (ValueError, TypeError):
        return False


class PluggableProtocolStateTracker(HasTraits):
    protocol_name = Str("untitled")
    loaded_protocol_path = File("")
    is_modified = Bool(False)

    # True while a protocol run is in flight. Set by the pane's button
    # state machine (the same transitions that flip btn_stop), so
    # non-view collaborators — e.g. the dock pane's repeat-duration
    # reconciliation — can gate on run state without touching Qt.
    is_active = Bool(False)

    modified_tag = Str(" [modified]")
    pkg_display_name = Str(PKG_name)

    # Duck-typed: anything with a writable `name` attribute. Avoids
    # importing pyface.DockPane just for an Instance() validator and
    # keeps the tracker headlessly testable with a plain stub.
    dock_pane = Any()

    # --- incremental diff state ---
    baseline_table = Instance(pd.DataFrame, allow_none=True)
    # frozenset of baseline path tuples; cached so on_structure_changed
    # doesn't rebuild it on every fire.
    baseline_paths = Any()
    # set[(path, col_id)] of cells currently differing from baseline.
    # In-place mutated by on_cell_changed; len() drives is_modified.
    dirty_cells = Any()
    # True when current path set != baseline path set. Incremental cell
    # updates are skipped while this is True (the path map is invalid);
    # on_structure_changed clears it via a full rescan once paths
    # re-align with baseline.
    structure_dirty = Bool(False)

    def traits_init(self):
        self.dirty_cells = set()
        self.baseline_paths = frozenset()
        # Empty baseline — any add/edit on the empty initial tree will
        # diverge and mark dirty. Reseed once the user saves/loads.
        self.baseline_table = pd.DataFrame()

    # --- display name ---

    def display_name(self) -> str:
        tag = self.modified_tag if self.is_modified else ""
        return f"{self.pkg_display_name} - {self.protocol_name}{tag}"

    def update_display_name(self) -> None:
        if self.dock_pane is None:
            return
        self.dock_pane.name = self.display_name()

    @observe("protocol_name, is_modified, dock_pane")
    def _on_display_relevant_change(self, event):
        self.update_display_name()

    # --- baseline + incremental API ---

    def reseed_baseline(self, manager) -> None:
        """Snapshot ``manager.table`` as the new baseline and clear
        all per-cell + structure dirty state. Called from save / load
        / new.
        """
        self.baseline_table = manager.table.copy()
        self.baseline_paths = frozenset(self.baseline_table.index)
        self.dirty_cells = set()
        self.structure_dirty = False
        self.is_modified = False

    def on_cell_changed(self, path, col_id, manager) -> None:
        """O(1) incremental: compare the one edited cell against
        baseline and add/remove from ``dirty_cells`` accordingly.

        Skipped while ``structure_dirty`` is True — the path -> baseline
        cell map isn't trustworthy until structure re-aligns and we
        rescan.
        """
        if self.structure_dirty:
            return
        path = tuple(path)
        if path not in self.baseline_paths:
            # Cell exists in current tree but not in baseline — would
            # mean we got cell_changed without the corresponding
            # structure update. Mark structure dirty as a safety net.
            self.structure_dirty = True
            self._recompute_is_modified()
            return
        try:
            current = manager.table.at[path, col_id]
            baseline = self.baseline_table.at[path, col_id]
        except KeyError:
            return
        key = (path, col_id)
        if _values_equal(current, baseline):
            self.dirty_cells.discard(key)
        else:
            self.dirty_cells.add(key)
        self._recompute_is_modified()

    def on_structure_changed(self, manager) -> None:
        """O(N) walk: compare current path set to baseline.

        If paths now match baseline, do a full rescan of cell values to
        rebuild ``dirty_cells`` from scratch (covers moves and bulk
        writes where cell_changed wasn't fired per cell). If paths
        differ, just flip ``structure_dirty`` — the rescan deferred
        until paths re-align.
        """
        current_paths = frozenset(p for p, _row in manager._walk())
        if current_paths == self.baseline_paths:
            self._rescan_dirty_cells(manager)
            self.structure_dirty = False
        else:
            self.structure_dirty = True
        self._recompute_is_modified()

    def _rescan_dirty_cells(self, manager) -> None:
        """Full O(N rows × M cols) compare; only called when paths
        match baseline (e.g. after move+undo or insert+delete)."""
        current = manager.table
        dirty = set()
        for path in self.baseline_paths:
            for col_id in self.baseline_table.columns:
                try:
                    cur_val = current.at[path, col_id]
                    base_val = self.baseline_table.at[path, col_id]
                except KeyError:
                    continue
                if not _values_equal(cur_val, base_val):
                    dirty.add((path, col_id))
        self.dirty_cells = dirty

    def _recompute_is_modified(self) -> None:
        self.is_modified = bool(self.dirty_cells) or self.structure_dirty

    # --- file lifecycle (filename + path only; baseline reseed is
    # done by the caller alongside these so a single manager.table
    # snapshot serves both record-keeping and diff bookkeeping). ---

    def set_loaded(self, file_path: str) -> None:
        if not file_path:
            raise ValueError("set_loaded requires a non-empty file path")
        path = Path(file_path)
        self.loaded_protocol_path = str(path)
        self.protocol_name = path.stem
        logger.info(
            f"Protocol loaded: {self.protocol_name} ({self.loaded_protocol_path})"
        )

    def set_saved(self, file_path: str) -> None:
        if not file_path:
            raise ValueError("set_saved requires a non-empty file path")
        path = Path(file_path)
        self.loaded_protocol_path = str(path)
        self.protocol_name = path.stem
        logger.info(
            f"Protocol saved: {self.protocol_name} ({self.loaded_protocol_path})"
        )

    def reset(self) -> None:
        """Reset filename / path traits to defaults. Baseline + dirty
        state are reset separately via ``reseed_baseline`` (which needs
        the manager handle)."""
        self.reset_traits(["protocol_name", "loaded_protocol_path"])
        self.dirty_cells = set()
        self.structure_dirty = False
        self.is_modified = False
