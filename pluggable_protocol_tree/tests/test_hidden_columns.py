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
    assert col.view.low == 1 and col.view.high == 64


def test_trail_overlay_column_metadata_and_hidden():
    col = make_trail_overlay_column()
    assert col.model.col_id == "trail_overlay"
    assert col.model.default_value == 0
    assert col.view.hidden_by_default is True
    assert col.view.low == 0 and col.view.high == 63


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


def test_repeat_duration_column_metadata_and_hidden():
    col = make_repeat_duration_column()
    assert col.model.col_id == "repeat_duration"
    assert col.model.default_value == 0.0
    assert col.view.hidden_by_default is True
    assert col.view.low == 0.0 and col.view.high == 3600.0


def test_linear_repeats_column_metadata_and_hidden():
    col = make_linear_repeats_column()
    assert col.model.col_id == "linear_repeats"
    assert col.model.default_value is False
    assert col.view.hidden_by_default is True
