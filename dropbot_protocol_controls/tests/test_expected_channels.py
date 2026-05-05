"""Pure helper that derives 'expected' channels from a step row + the
electrode_to_channel mapping. Mirrors legacy
_get_expected_droplet_channels (protocol_runner_controller.py:1763)."""

import pytest
from traits.api import HasTraits, List, Str

from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    expected_channels_for_step,
)


class _FakeRow(HasTraits):
    electrodes = List(Str)
    routes               = List  # List[List[Str]]


# A small fixed mapping used across most tests.
MAP = {"e1": 1, "e2": 2, "e3": 3, "e4": 4, "e5": 5, "e6": 6}


def test_empty_step_returns_empty_list():
    assert expected_channels_for_step(_FakeRow(), MAP) == []


def test_only_electrodes():
    row = _FakeRow(electrodes=["e1", "e2"])
    assert expected_channels_for_step(row, MAP) == [1, 2]


def test_only_routes_takes_last_electrode_of_each():
    row = _FakeRow(routes=[["e1", "e2", "e3"], ["e4", "e5"]])
    assert expected_channels_for_step(row, MAP) == [3, 5]


def test_activated_and_routes_are_unioned():
    row = _FakeRow(
        electrodes=["e1"],
        routes=[["e2", "e3"]],
    )
    assert expected_channels_for_step(row, MAP) == [1, 3]


def test_duplicate_channels_are_deduplicated():
    # Activated includes e3, route also ends at e3.
    row = _FakeRow(
        electrodes=["e1", "e3"],
        routes=[["e2", "e3"]],
    )
    assert expected_channels_for_step(row, MAP) == [1, 3]


def test_result_is_sorted():
    row = _FakeRow(electrodes=["e5", "e2", "e4", "e1"])
    assert expected_channels_for_step(row, MAP) == [1, 2, 4, 5]


def test_unknown_electrode_id_is_silently_dropped():
    # 'e99' isn't in the mapping — drop it, don't crash.
    row = _FakeRow(electrodes=["e1", "e99", "e2"])
    assert expected_channels_for_step(row, MAP) == [1, 2]


def test_route_with_unknown_last_electrode_is_silently_dropped():
    row = _FakeRow(routes=[["e1", "e99"], ["e2", "e3"]])
    # First route's last 'e99' missing → dropped. Second route ends 'e3'.
    assert expected_channels_for_step(row, MAP) == [3]


def test_empty_route_inside_routes_list_is_skipped():
    # Defensive: a route with zero electrodes should not crash on route[-1].
    row = _FakeRow(routes=[[], ["e2", "e3"]])
    assert expected_channels_for_step(row, MAP) == [3]


def test_empty_mapping_returns_empty_list_even_with_inputs():
    row = _FakeRow(electrodes=["e1"], routes=[["e2", "e3"]])
    assert expected_channels_for_step(row, {}) == []
