"""Unit tests for PluggableProtocolStateTracker.

No Qt or DockPane required — the tracker accepts a stub object with a
writable ``name`` attribute for title-rewrite tests, and a real
``RowManager`` for the incremental-diff path (RowManager itself is
HasTraits-only).
"""

import pytest

from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import PKG_name
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)


class _NameStub:
    """Stand-in for a DockPane — only ``name`` matters for these tests."""
    def __init__(self):
        self.name = ""


def _make_manager():
    return RowManager(columns=[make_type_column(), make_name_column()])


# --- defaults / display name ----------------------------------------

def test_defaults():
    t = PluggableProtocolStateTracker()
    assert t.protocol_name == "untitled"
    assert t.loaded_protocol_path == ""
    assert t.is_modified is False
    assert t.modified_tag == " [modified]"


def test_display_name_clean_dirty_and_untitled():
    t = PluggableProtocolStateTracker()
    assert t.display_name() == f"{PKG_name} - untitled"
    t.protocol_name = "my_assay"
    assert t.display_name() == f"{PKG_name} - my_assay"
    t.is_modified = True
    assert t.display_name() == f"{PKG_name} - my_assay [modified]"


def test_no_dock_pane_is_safe():
    """Tracker should be usable headlessly without a dock_pane."""
    t = PluggableProtocolStateTracker()
    t.protocol_name = "demo"      # no crash
    t.is_modified = True          # no crash
    assert t.display_name() == f"{PKG_name} - demo [modified]"


def test_dock_pane_name_rewritten_on_name_change():
    stub = _NameStub()
    t = PluggableProtocolStateTracker(dock_pane=stub)
    assert stub.name == f"{PKG_name} - untitled"
    t.protocol_name = "demo"
    assert stub.name == f"{PKG_name} - demo"


def test_dock_pane_name_rewritten_on_dirty_change():
    stub = _NameStub()
    t = PluggableProtocolStateTracker(dock_pane=stub)
    t.protocol_name = "demo"
    t.is_modified = True
    assert stub.name == f"{PKG_name} - demo [modified]"
    t.is_modified = False
    assert stub.name == f"{PKG_name} - demo"


# --- file lifecycle (filename only; dirty is separate) --------------

def test_set_loaded_sets_name_and_path():
    t = PluggableProtocolStateTracker()
    t.set_loaded("/tmp/some/path/my_assay.json")
    assert t.protocol_name == "my_assay"
    assert "my_assay.json" in t.loaded_protocol_path


def test_set_saved_sets_name_and_path():
    t = PluggableProtocolStateTracker()
    t.set_saved("/tmp/x/another.json")
    assert t.protocol_name == "another"


def test_set_loaded_rejects_empty_path():
    t = PluggableProtocolStateTracker()
    with pytest.raises(ValueError):
        t.set_loaded("")


def test_reset_returns_defaults():
    t = PluggableProtocolStateTracker()
    t.set_loaded("/tmp/x/foo.json")
    t.is_modified = True
    t.reset()
    assert t.protocol_name == "untitled"
    assert t.loaded_protocol_path == ""
    assert t.is_modified is False


# --- incremental diff against baseline -------------------------------

def test_reseed_clears_dirty_state():
    mgr = _make_manager()
    mgr.add_step(values={"name": "a"})
    t = PluggableProtocolStateTracker()
    # Simulate prior structural mutation - tracker would mark dirty.
    t.on_structure_changed(mgr)
    assert t.is_modified is True

    t.reseed_baseline(mgr)
    assert t.is_modified is False
    assert len(t.dirty_cells) == 0
    assert t.structure_dirty is False


def test_cell_edit_marks_dirty_when_diff_from_baseline():
    mgr = _make_manager()
    path = mgr.add_step(values={"name": "before"})
    t = PluggableProtocolStateTracker()
    t.reseed_baseline(mgr)

    row = mgr.get_row(path)
    row.name = "after"
    t.on_cell_changed(path, "name", mgr)

    assert t.is_modified is True
    assert (path, "name") in t.dirty_cells


def test_cell_revert_clears_dirty():
    """Editing back to the baseline value removes the cell from
    dirty_cells and clears is_modified when nothing else differs."""
    mgr = _make_manager()
    path = mgr.add_step(values={"name": "before"})
    t = PluggableProtocolStateTracker()
    t.reseed_baseline(mgr)

    row = mgr.get_row(path)
    row.name = "after"
    t.on_cell_changed(path, "name", mgr)
    assert t.is_modified is True

    row.name = "before"     # revert
    t.on_cell_changed(path, "name", mgr)
    assert t.is_modified is False
    assert (path, "name") not in t.dirty_cells


def test_two_diffs_then_revert_one_still_dirty():
    """dirty_cells is a set: removing one entry doesn't clear the
    other. Mixed revert keeps is_modified True until both revert."""
    mgr = _make_manager()
    p1 = mgr.add_step(values={"name": "A"})
    p2 = mgr.add_step(values={"name": "B"})
    t = PluggableProtocolStateTracker()
    t.reseed_baseline(mgr)

    mgr.get_row(p1).name = "A2"
    t.on_cell_changed(p1, "name", mgr)
    mgr.get_row(p2).name = "B2"
    t.on_cell_changed(p2, "name", mgr)
    assert t.is_modified is True
    assert len(t.dirty_cells) == 2

    mgr.get_row(p1).name = "A"      # revert one
    t.on_cell_changed(p1, "name", mgr)
    assert t.is_modified is True
    assert len(t.dirty_cells) == 1


def test_insert_then_delete_clears_dirty():
    """Add a step then remove it -> path set matches baseline ->
    rescan finds no diffs -> dirty clears."""
    mgr = _make_manager()
    mgr.add_step(values={"name": "kept"})
    t = PluggableProtocolStateTracker()
    t.reseed_baseline(mgr)

    new_path = mgr.add_step(values={"name": "transient"})
    t.on_structure_changed(mgr)
    assert t.is_modified is True
    assert t.structure_dirty is True

    mgr.remove([new_path])
    t.on_structure_changed(mgr)
    assert t.is_modified is False
    assert t.structure_dirty is False


def test_move_then_undo_clears_dirty():
    """Reorder two steps then reorder back -> path set always matches
    baseline (count unchanged), but the rescan on rows_changed detects
    that values at each path match baseline again."""
    mgr = _make_manager()
    p1 = mgr.add_step(values={"name": "A"})    # A at (0,)
    mgr.add_step(values={"name": "B"})         # B at (1,)
    t = PluggableProtocolStateTracker()
    t.reseed_baseline(mgr)

    # Move A from (0,) to the end. After: B at (0,), A at (1,).
    mgr.move([p1], target_parent_path=(), target_index=2)
    t.on_structure_changed(mgr)
    assert t.is_modified is True   # contents at (0,)/(1,) swapped

    # Now move what is at (1,) (the A row again) back to position 0.
    # After: A at (0,), B at (1,) — baseline order restored.
    mgr.move([(1,)], target_parent_path=(), target_index=0)
    t.on_structure_changed(mgr)
    assert mgr.get_row((0,)).name == "A"
    assert mgr.get_row((1,)).name == "B"
    assert t.is_modified is False


def test_structure_change_skips_cell_increment():
    """While structure_dirty is True the per-cell increment is a
    no-op (path -> baseline map isn't valid)."""
    mgr = _make_manager()
    p1 = mgr.add_step(values={"name": "A"})
    t = PluggableProtocolStateTracker()
    t.reseed_baseline(mgr)

    # Cause a structure-mismatch.
    p2 = mgr.add_step(values={"name": "B"})
    t.on_structure_changed(mgr)
    assert t.structure_dirty is True

    # Edit a cell while structure-dirty — dirty_cells stays unchanged.
    mgr.get_row(p1).name = "edited"
    t.on_cell_changed(p1, "name", mgr)
    assert len(t.dirty_cells) == 0
    assert t.is_modified is True   # held by structure_dirty
