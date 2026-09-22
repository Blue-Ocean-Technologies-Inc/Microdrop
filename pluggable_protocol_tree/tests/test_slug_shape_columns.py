# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The slug shape's four hidden columns (#682) and their mapping to and
from the device viewer sidebar's step parameters."""

# Standard library imports.
from types import SimpleNamespace

# Local imports.
from ..builtins.lane_left_column import make_lane_left_column
from ..builtins.lane_right_column import make_lane_right_column
from ..builtins.lanes_in_out_column import make_lanes_in_out_column
from ..builtins.rotation_lock_column import make_rotation_lock_column
from ..plugin import PluggableProtocolTreePlugin
from ..services.device_viewer_sync import (
    _col_values_from_execution_params,
    _execution_params_for_row,
)

SIDEBAR_PARAMS = {
    "duration": 1.0,
    "repetitions": 1,
    "repeat_duration": 0,
    "trail_length": 1,
    "trail_overlay": 0,
    "soft_start": False,
    "soft_terminate": False,
    "linear_repeats": False,
}


def test_the_four_shape_columns_are_hidden_with_plain_trail_defaults():
    lanes_in = make_lane_left_column()
    lanes_out = make_lane_right_column()
    in_out = make_lanes_in_out_column()
    lock = make_rotation_lock_column()

    assert [c.model.col_id for c in (lanes_in, lanes_out, in_out, lock)] == [
        "lane_left",
        "lane_right",
        "lanes_in_out",
        "rotation_lock",
    ]
    assert all(c.view.hidden_by_default for c in (lanes_in, lanes_out, in_out, lock))
    assert lanes_in.model.default_value == 0 and lanes_out.model.default_value == 0
    assert in_out.model.default_value is True and lock.model.default_value is True
    # Bounds mirror the DV sidebar's RouteLayerManager lane ranges.
    assert lanes_in.view.low == 0 and lanes_in.view.high == 20


def test_the_plugin_assembles_the_shape_columns_after_linear_repeats():
    ids = [c.model.col_id for c in PluggableProtocolTreePlugin()._assemble_columns()]

    assert ids.index("linear_repeats") < ids.index("lane_left")
    assert ids[ids.index("lane_left") : ids.index("lane_left") + 4] == [
        "lane_left",
        "lane_right",
        "lanes_in_out",
        "rotation_lock",
    ]


def test_sidebar_params_map_onto_the_shape_columns_and_back():
    values = _col_values_from_execution_params(
        {**SIDEBAR_PARAMS, "lane_left": 2, "lane_right": 1, "rotation_lock": False}
    )

    assert (values["lane_left"], values["lane_right"]) == (2, 1)
    assert values["lanes_in_out"] is True and values["rotation_lock"] is False

    row = SimpleNamespace(
        repeat_duration_controls=False,
        route_repetitions=1,
        duration_s=1.0,
        lane_left=2,
        lane_right=1,
        lanes_in_out=True,
        rotation_lock=False,
    )
    params = _execution_params_for_row(row)

    assert (params["lane_left"], params["lane_right"]) == (2, 1)
    assert params["lanes_in_out"] is True and params["rotation_lock"] is False


def test_senders_and_rows_without_the_shape_read_as_a_plain_trail():
    values = _col_values_from_execution_params(SIDEBAR_PARAMS)
    params = _execution_params_for_row(
        SimpleNamespace(repeat_duration_controls=False, route_repetitions=1)
    )

    for shape in (values, params):
        assert (shape["lane_left"], shape["lane_right"]) == (0, 0)
        assert shape["lanes_in_out"] is True and shape["rotation_lock"] is True


def test_a_contributed_column_with_a_builtin_id_is_dropped():
    plugin = PluggableProtocolTreePlugin(contributed_columns=[make_lane_left_column()])
    ids = [c.model.col_id for c in plugin._assemble_columns()]

    assert ids.count("lane_left") == 1 and len(ids) == len(set(ids))
