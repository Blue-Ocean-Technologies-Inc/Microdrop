# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for RowManager.rebuild_columns and the column-value stash (issue
#641 step 2): the row-data work behind the dock pane's runtime column
hot load/unload (the magnet-column scenario)."""

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager


@pytest.fixture
def columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_duration_column(),
    ]


@pytest.fixture
def manager(columns):
    return RowManager(columns=columns)


def _duration_column(manager):
    return next(c for c in manager.columns if c.model.col_id == "duration_s")


# --- rebuild_columns -------------------------------------------------------


def test_rebuild_columns_reports_removed_and_added_ids(manager):
    duration_col = _duration_column(manager)
    remaining = [c for c in manager.columns if c is not duration_col]

    added, removed = manager.rebuild_columns(remaining)
    assert removed == {"duration_s"}
    assert added == set()

    added, removed = manager.rebuild_columns(remaining + [duration_col])
    assert removed == set()
    assert added == {"duration_s"}


def test_rebuild_columns_preserves_common_column_values(manager):
    p = manager.add_step(values={"name": "A", "duration_s": 3.5})

    manager.rebuild_columns(list(manager.columns))  # same set: pure round trip

    row = manager.get_row(p)
    assert row.name == "A"
    assert row.duration_s == 3.5


def test_rebuild_columns_remove_then_readd_restores_stashed_value(manager):
    """Live remove -> re-add toggle (the magnet-column scenario, issue #641
    step 2): dropping a column stashes its per-row values by uuid, and
    re-adding the same column later restores them even though the rebuilt
    tree's rows are freshly deserialized objects, not the originals."""
    p = manager.add_step(values={"name": "A", "duration_s": 7.5})
    duration_col = _duration_column(manager)
    remaining = [c for c in manager.columns if c is not duration_col]

    manager.rebuild_columns(remaining)
    assert not hasattr(manager.get_row(p), "duration_s")

    manager.rebuild_columns(remaining + [duration_col])
    assert manager.get_row(p).duration_s == 7.5


def test_rebuild_columns_stash_keyed_by_uuid_across_multiple_rows(manager):
    a = manager.add_step(values={"name": "A", "duration_s": 1.5})
    b = manager.add_step(values={"name": "B", "duration_s": 9.5})
    duration_col = _duration_column(manager)
    remaining = [c for c in manager.columns if c is not duration_col]

    manager.rebuild_columns(remaining)
    manager.rebuild_columns(remaining + [duration_col])

    assert manager.get_row(a).duration_s == 1.5
    assert manager.get_row(b).duration_s == 9.5


# --- stash_column_values / restore_stashed_column_values -------------------


def test_stash_and_restore_column_values_directly(manager):
    p = manager.add_step(values={"name": "A", "duration_s": 4.0})
    row_uuid = manager.get_row(p).uuid

    manager.stash_column_values(["duration_s"])
    assert manager.column_value_stash[row_uuid] == {"duration_s": 4.0}

    manager.get_row(p).duration_s = 0.0
    manager.restore_stashed_column_values(["duration_s"])
    assert manager.get_row(p).duration_s == 4.0


def test_restore_stashed_column_values_is_noop_without_a_stash(manager):
    p = manager.add_step(values={"name": "A", "duration_s": 2.0})

    manager.restore_stashed_column_values(["duration_s"])

    assert manager.get_row(p).duration_s == 2.0
