# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the PMT step-capture value contract: tolerant parse,
normalisation (tick-filtering) on write, phase slicing, and the display
summary."""

# Microdrop package imports.
from portable_dropbot_protocol_controls.pmt_step_capture import (
    normalize_step_capture,
    parse_step_capture,
    summary_text,
)

ENTRY_START = {
    "slot": 1,
    "gain": 100,
    "exposure_s": 5.0,
    "at_start": True,
    "at_end": False,
}
ENTRY_END = {
    "slot": 2,
    "gain": 150,
    "exposure_s": 8.0,
    "at_start": False,
    "at_end": True,
}
ENTRY_BOTH = {
    "slot": 3,
    "gain": 200,
    "exposure_s": 3.0,
    "at_start": True,
    "at_end": True,
}
ENTRY_NEITHER = {
    "slot": 4,
    "gain": 50,
    "exposure_s": 1.0,
    "at_start": False,
    "at_end": False,
}

STEP_VALUE = {
    "avg": 16,
    "osr": 6,
    "rf_ohms": 499000.0,
    "entries": [ENTRY_START, ENTRY_END, ENTRY_BOTH],
}


def test_parse_step_capture_none_and_empty_dict_are_no_capture():
    assert parse_step_capture(None) is None
    assert parse_step_capture({}) is None


def test_parse_step_capture_round_trips_a_valid_cell():
    step = parse_step_capture(STEP_VALUE)

    assert step.avg == 16
    assert step.osr == 6
    assert step.rf_ohms == 499000.0
    assert [e.slot for e in step.entries] == [1, 2, 3]


def test_parse_step_capture_invalid_cell_logs_and_reads_as_none(caplog):
    value = {"entries": [{"slot": 99, "gain": 100, "exposure_s": 5.0}]}

    assert parse_step_capture(value) is None
    assert "Skipping invalid PMT step capture" in caplog.text


def test_normalize_step_capture_drops_entries_with_neither_tick():
    normalized = normalize_step_capture(
        {**STEP_VALUE, "entries": [ENTRY_START, ENTRY_NEITHER]}
    )

    assert [e["slot"] for e in normalized["entries"]] == [1]


def test_normalize_step_capture_all_unticked_collapses_to_none():
    assert normalize_step_capture({**STEP_VALUE, "entries": [ENTRY_NEITHER]}) is None


def test_normalize_step_capture_none_stays_none():
    assert normalize_step_capture(None) is None


def test_normalize_step_capture_preserves_order():
    normalized = normalize_step_capture(STEP_VALUE)
    assert [e["slot"] for e in normalized["entries"]] == [1, 2, 3]


def test_summary_text_blank_for_no_capture():
    assert summary_text(None) == ""
    assert summary_text({}) == ""


def test_summary_text_counts_spots_and_phases():
    assert summary_text(STEP_VALUE) == "3 spots · 2 start / 2 end"


def test_summary_text_singular_spot():
    single = {**STEP_VALUE, "entries": [ENTRY_START]}
    assert summary_text(single) == "1 spot · 1 start / 0 end"
