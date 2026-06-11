"""Tests for the 6 hidden-by-default trail/loop/ramp config columns
shipped by the core plugin in PPT-3."""

from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.soft_end_column import (
    make_soft_end_column,
)
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
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
    return RowManager(columns=[
        make_name_column(),
        make_trail_length_column(),
        make_trail_overlay_column(),
    ])


def test_trail_overlay_handler_clamps_to_trail_length(qapp):
    manager = _trail_manager()
    manager.add_step(values={"name": "S1", "trail_length": 4})
    row = manager.get_row((0,))
    col = manager.columns[2]
    assert col.handler.on_interact(row, col.model, 99) is True
    assert row.trail_overlay == 3                 # trail_length - 1
    assert col.handler.on_interact(row, col.model, 2) is True
    assert row.trail_overlay == 2                 # in-range passes through


def test_trail_overlay_editor_max_follows_row_trail_length(qapp):
    manager = _trail_manager()
    manager.add_step(values={"name": "S1", "trail_length": 5})
    row = manager.get_row((0,))
    view = manager.columns[2].view
    editor = view.create_editor(None, row)
    assert editor.maximum() == 4                  # trail_length - 1
    editor_no_ctx = view.create_editor(None, None)
    assert editor_no_ctx.maximum() == view.high   # static fallback


def test_shrinking_trail_length_drags_overlay_down(qapp):
    """Pane-level clamp: lowering Trail Len below overlay + 1 clamps the
    overlay cell too, with a cell_changed event for dirty tracking."""
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )

    pane = ProtocolTreePane([
        make_type_column(), make_name_column(),
        make_trail_length_column(), make_trail_overlay_column(),
    ])
    pane.manager.add_step(values={
        "name": "S1", "trail_length": 10, "trail_overlay": 7,
    })
    row = pane.manager.get_row((0,))

    pane.manager.set_value((0,), "trail_length", 3)
    assert row.trail_overlay == 2                 # dragged down to length - 1

    pane.manager.set_value((0,), "trail_length", 8)
    assert row.trail_overlay == 2                 # growing length leaves it
