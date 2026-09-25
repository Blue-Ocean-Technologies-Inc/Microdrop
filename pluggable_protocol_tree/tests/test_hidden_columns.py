# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the 6 hidden-by-default trail/loop/ramp config columns
shipped by the core plugin in PPT-3."""

# Microdrop package imports.
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.soft_end_column import (
    make_soft_end_column,
)
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)


def test_trail_length_column_metadata_and_hidden():
    col = make_trail_length_column()
    assert col.model.col_id == "trail_length"
    assert col.model.col_name == "Trail Len"
    assert col.model.default_value == 1
    assert col.view.hidden_by_default is True
    # Bounds mirror the DV sidebar's RouteLayerManager.trail_length.
    assert col.view.low == 1 and col.view.high == 10000


def test_trail_overlay_column_metadata_and_hidden():
    col = make_trail_overlay_column()
    assert col.model.col_id == "trail_overlay"
    assert col.model.default_value == 0
    assert col.view.hidden_by_default is True
    assert col.view.low == 0 and col.view.high == 10000


def test_soft_start_column_metadata_and_hidden():
    col = make_soft_start_column()
    assert col.model.col_id == "soft_start"
    assert col.model.default_value is False
    assert col.view.hidden_by_default is True


def test_soft_end_column_metadata_and_hidden():
    col = make_soft_end_column()
    assert col.model.col_id == "soft_end"
    assert col.model.default_value is False
    assert col.view.hidden_by_default is True


def test_repeat_duration_column_metadata_and_visible():
    col = make_repeat_duration_column()
    assert col.model.col_id == "repeat_duration"
    assert col.model.col_name == "Route Reps Dur"
    assert col.model.default_value == 0.0
    assert col.view.hidden_by_default is False
    # Bounds mirror the DV sidebar's RouteLayerManager.repeat_duration.
    assert col.view.low == 0.0 and col.view.high == 10000.0


def test_linear_repeats_column_metadata_and_hidden():
    col = make_linear_repeats_column()
    assert col.model.col_id == "linear_repeats"
    assert col.model.default_value is False
    assert col.view.hidden_by_default is True


# --- trail_overlay <= trail_length - 1 (mirrors the DV sidebar's dynamic
# --- max_trail_overlay Range bound, issue #435 review) --------------------


def _trail_manager():
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.row_manager import RowManager

    return RowManager(
        columns=[
            make_name_column(),
            make_trail_length_column(),
            make_trail_overlay_column(),
        ]
    )


def test_trail_overlay_handler_clamps_to_trail_length(qapp):
    manager = _trail_manager()
    manager.add_step(values={"name": "S1", "trail_length": 4})
    row = manager.get_row((0,))
    col = manager.columns[2]
    assert col.handler.on_interact(row, col.model, 99) is True
    assert row.trail_overlay == 3  # trail_length - 1
    assert col.handler.on_interact(row, col.model, 2) is True
    assert row.trail_overlay == 2  # in-range passes through


def test_trail_overlay_editor_max_follows_row_trail_length(qapp):
    manager = _trail_manager()
    manager.add_step(values={"name": "S1", "trail_length": 5})
    row = manager.get_row((0,))
    view = manager.columns[2].view
    editor = view.create_editor(None, row)
    assert editor.maximum() == 4  # trail_length - 1
    editor_no_ctx = view.create_editor(None, None)
    assert editor_no_ctx.maximum() == view.high  # static fallback


def _build_dock_pane(columns):
    """Minimal headless PluggableProtocolDockPane: a real (but plugin-free)
    Envisage Task/TaskWindow/Application chain so the strictly-typed `task`
    trait validates, plus the two application traits
    (`current_experiment_directory`, `experiment_changed`) the dock pane's
    class-level `@observe("task.window.application...")` decorators need to
    exist at construction time. The real `MicrodropApplication` declares
    these too, but as filesystem-backed Properties — overkill (and file
    I/O) for a pure unit test."""
    from envisage.ui.tasks.api import TasksApplication, TaskWindow
    from pyface.tasks.api import Task
    from traits.api import Any, Event

    from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane

    class _StubApplication(TasksApplication):
        experiment_changed = Event()
        current_experiment_directory = Any(None)

    task = Task()
    task.window = TaskWindow(application=_StubApplication())

    dock_pane = PluggableProtocolDockPane(columns=columns, task=task)
    dock_pane.create_contents(parent=None)

    return dock_pane


def test_shrinking_trail_length_drags_overlay_down(qapp):
    """Dock-pane-level clamp (issue #471 moved run control off the pane):
    lowering Trail Len below overlay + 1 clamps the overlay cell too, with
    a cell_changed event for dirty tracking."""
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dock_pane = _build_dock_pane(
        [
            make_type_column(),
            make_name_column(),
            make_trail_length_column(),
            make_trail_overlay_column(),
        ]
    )
    manager = dock_pane.manager
    manager.add_step(values={"name": "S1"})
    row = manager.get_row((0,))
    # Set trail_length and trail_overlay as separate cell edits (as the UI
    # would), not a single add_step(values=...) bulk write — the clamp only
    # reacts to a "trail_length" cell_changed event, so setting both at once
    # would clamp overlay against trail_length's still-default value.
    manager.set_value((0,), "trail_length", 10)
    manager.set_value((0,), "trail_overlay", 7)
    qapp.processEvents()

    manager.set_value((0,), "trail_length", 3)
    qapp.processEvents()
    assert row.trail_overlay == 2  # dragged down to length - 1

    manager.set_value((0,), "trail_length", 8)
    qapp.processEvents()
    assert row.trail_overlay == 2  # growing length leaves it
