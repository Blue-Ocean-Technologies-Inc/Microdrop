# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the fluorescence step-capture value contract: tolerant parse,
normalisation (tick-filtering) on write, phase slicing, and the display
summary. Mirrors test_pmt_step_capture.py."""

# Microdrop package imports.
from portable_dropbot_protocol_controls.fluorescence_step_capture import (
    normalize_step_capture,
    parse_step_capture,
    summary_text,
)

ENTRY_START = {
    "filter_position": 1,
    "led_percent": 50,
    "exposure_ms": 50.0,
    "focus_distance": None,
    "at_start": True,
    "at_end": False,
}
ENTRY_END = {
    "filter_position": 2,
    "led_percent": 60,
    "exposure_ms": 40.0,
    "focus_distance": 0.5,
    "at_start": False,
    "at_end": True,
}
ENTRY_BOTH = {
    "filter_position": 3,
    "led_percent": 70,
    "exposure_ms": 30.0,
    "focus_distance": None,
    "at_start": True,
    "at_end": True,
}
ENTRY_NEITHER = {
    "filter_position": 4,
    "led_percent": 10,
    "exposure_ms": 20.0,
    "focus_distance": None,
    "at_start": False,
    "at_end": False,
}

STEP_VALUE = {"entries": [ENTRY_START, ENTRY_END, ENTRY_BOTH]}


def test_parse_step_capture_none_and_empty_dict_are_no_capture():
    assert parse_step_capture(None) is None
    assert parse_step_capture({}) is None


def test_parse_step_capture_round_trips_a_valid_cell():
    step = parse_step_capture(STEP_VALUE)

    assert [e.filter_position for e in step.entries] == [1, 2, 3]
    assert step.entries[1].focus_distance == 0.5


def test_parse_step_capture_invalid_cell_logs_and_reads_as_none(caplog):
    value = {"entries": [{"filter_position": "not-a-position", "led_percent": 50}]}

    assert parse_step_capture(value) is None
    assert "Skipping invalid fluorescence step capture" in caplog.text


def test_normalize_step_capture_drops_entries_with_neither_tick():
    normalized = normalize_step_capture({"entries": [ENTRY_START, ENTRY_NEITHER]})

    assert [e["filter_position"] for e in normalized["entries"]] == [1]


def test_normalize_step_capture_all_unticked_collapses_to_none():
    assert normalize_step_capture({"entries": [ENTRY_NEITHER]}) is None


def test_normalize_step_capture_none_stays_none():
    assert normalize_step_capture(None) is None


def test_normalize_step_capture_preserves_order():
    normalized = normalize_step_capture(STEP_VALUE)
    assert [e["filter_position"] for e in normalized["entries"]] == [1, 2, 3]


def test_summary_text_blank_for_no_capture():
    assert summary_text(None) == ""
    assert summary_text({}) == ""


def test_summary_text_counts_filters_and_phases():
    # 2 filters: one ticked both, one ticked end only -> 1 start / 2 end,
    # matching the spec's example summary exactly.
    step = {"entries": [ENTRY_BOTH, ENTRY_END]}
    assert summary_text(step) == "2 filters · 1 start / 2 end"


def test_summary_text_singular_filter():
    single = {"entries": [ENTRY_START]}
    assert summary_text(single) == "1 filter · 1 start / 0 end"
