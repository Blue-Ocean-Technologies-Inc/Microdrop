# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the repeat-duration / trail-overlay reconciler (issue #641
step 1). The geometry math (``estimate_repeat_duration_s`` /
``effective_repetitions_for_duration``) has its own coverage in
test_phase_math.py; these tests mock those collaborators so they isolate
the reconciler's own decision logic (which mode, which trigger, the
tolerance/clamp arithmetic, the cell_changed event)."""

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.route_repetitions_column import (
    make_route_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services import repeat_duration_reconciler as reconciler


@pytest.fixture
def manager():
    return RowManager(
        columns=[
            make_name_column(),
            make_duration_column(),
            make_trail_length_column(),
            make_trail_overlay_column(),
            make_routes_column(),
            make_repeat_duration_column(),
            make_route_repetitions_column(),
        ]
    )


# --- clamp_trail_overlay_for_row -----------------------------------------


def test_clamp_ignores_unrelated_columns(manager):
    path = manager.add_step(values={"name": "S1", "trail_overlay": 7})
    reconciler.clamp_trail_overlay_for_row(manager, path, "name")
    assert manager.get_row(path).trail_overlay == 7


def test_clamp_drags_overlay_down_when_out_of_range(manager):
    path = manager.add_step(
        values={"name": "S1", "trail_length": 10, "trail_overlay": 7}
    )
    manager.set_value(path, "trail_length", 3)
    reconciler.clamp_trail_overlay_for_row(manager, path, "trail_length")
    assert manager.get_row(path).trail_overlay == 2  # trail_length - 1


def test_clamp_leaves_in_range_overlay_untouched(manager):
    path = manager.add_step(
        values={"name": "S1", "trail_length": 10, "trail_overlay": 2}
    )
    reconciler.clamp_trail_overlay_for_row(manager, path, "trail_length")
    assert manager.get_row(path).trail_overlay == 2


def test_clamp_fires_cell_changed_only_when_it_writes(manager):
    path = manager.add_step(
        values={"name": "S1", "trail_length": 3, "trail_overlay": 7}
    )
    events = []
    manager.observe(lambda event: events.append(event.new), "cell_changed")

    reconciler.clamp_trail_overlay_for_row(manager, path, "trail_length")
    assert events == [{"path": tuple(path), "col_id": "trail_overlay"}]

    events.clear()
    reconciler.clamp_trail_overlay_for_row(manager, path, "trail_length")
    assert events == []  # already in range, no-op


def test_clamp_ignores_a_stale_path(manager):
    # No rows exist yet -- get_row raises IndexError, which is caught.
    reconciler.clamp_trail_overlay_for_row(manager, (0,), "trail_length")


# --- reconcile_repeat_duration_for_row ------------------------------------


def _add_row_with_route(manager, **overrides):
    values = {
        "name": "S1",
        "routes": [["e000", "e001", "e002"]],
        "duration_s": 1.0,
        "trail_length": 1,
        "trail_overlay": 0,
        "route_repetitions": 2,
        "repeat_duration": 0.0,
    }
    values.update(overrides)
    return manager.add_step(values=values)


def test_reconcile_skipped_while_protocol_active(manager, monkeypatch):
    path = _add_row_with_route(manager)
    called = []
    monkeypatch.setattr(
        reconciler, "estimate_repeat_duration_s", lambda **kw: called.append(kw) or 5.0
    )
    reconciler.reconcile_repeat_duration_for_row(
        manager, path, "duration_s", is_protocol_active=True
    )
    assert called == []
    assert manager.get_row(path).repeat_duration == 0.0


def test_reconcile_skipped_when_row_has_no_routes(manager, monkeypatch):
    path = manager.add_step(values={"name": "S1", "routes": []})
    called = []
    monkeypatch.setattr(
        reconciler, "estimate_repeat_duration_s", lambda **kw: called.append(kw) or 5.0
    )
    reconciler.reconcile_repeat_duration_for_row(
        manager, path, "duration_s", is_protocol_active=False
    )
    assert called == []


def test_reconcile_refreshes_repeat_duration_in_route_reps_mode(manager, monkeypatch):
    path = _add_row_with_route(manager)
    monkeypatch.setattr(reconciler, "estimate_repeat_duration_s", lambda **kw: 3.456)

    events = []
    manager.observe(lambda event: events.append(event.new), "cell_changed")
    reconciler.reconcile_repeat_duration_for_row(
        manager, path, "duration_s", is_protocol_active=False
    )

    row = manager.get_row(path)
    assert row.repeat_duration == 3.46  # rounded to REPEAT_DURATION_DECIMALS
    assert events == [{"path": tuple(path), "col_id": "repeat_duration"}]


def test_reconcile_ignores_a_non_trigger_column(manager, monkeypatch):
    path = _add_row_with_route(manager)
    called = []
    monkeypatch.setattr(
        reconciler, "estimate_repeat_duration_s", lambda **kw: called.append(kw) or 9.0
    )
    reconciler.reconcile_repeat_duration_for_row(
        manager, path, "name", is_protocol_active=False
    )
    assert called == []


def test_reconcile_skips_write_within_tolerance(manager, monkeypatch):
    path = _add_row_with_route(manager, repeat_duration=3.46)
    monkeypatch.setattr(reconciler, "estimate_repeat_duration_s", lambda **kw: 3.4601)

    events = []
    manager.observe(lambda event: events.append(event.new), "cell_changed")
    reconciler.reconcile_repeat_duration_for_row(
        manager, path, "duration_s", is_protocol_active=False
    )

    assert manager.get_row(path).repeat_duration == 3.46  # unchanged
    assert events == []


def test_reconcile_refreshes_route_repetitions_in_duration_mode(manager, monkeypatch):
    path = _add_row_with_route(manager, repeat_duration_controls=True)
    monkeypatch.setattr(
        reconciler, "effective_repetitions_for_duration", lambda **kw: 5
    )

    events = []
    manager.observe(lambda event: events.append(event.new), "cell_changed")
    reconciler.reconcile_repeat_duration_for_row(
        manager, path, "repeat_duration", is_protocol_active=False
    )

    row = manager.get_row(path)
    assert row.route_repetitions == 5
    assert events == [{"path": tuple(path), "col_id": "route_repetitions"}]


def test_reconcile_duration_mode_ignores_other_columns(manager, monkeypatch):
    path = _add_row_with_route(manager, repeat_duration_controls=True)
    called = []
    monkeypatch.setattr(
        reconciler,
        "effective_repetitions_for_duration",
        lambda **kw: called.append(kw) or 5,
    )
    reconciler.reconcile_repeat_duration_for_row(
        manager, path, "duration_s", is_protocol_active=False
    )
    assert called == []
