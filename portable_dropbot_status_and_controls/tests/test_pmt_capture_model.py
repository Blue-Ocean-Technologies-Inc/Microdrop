# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The PMT Capture pane model's two pure rules: merging a fresh spot list
into the existing rows, and turning ticked rows into the request payload."""

# Microdrop package imports.
from portable_dropbot_controller.consts import DEFAULT_PMT_EXPOSURE_S, DEFAULT_PMT_GAIN
from portable_dropbot_status_and_controls.models.pmt_capture_model import (
    PmtSpotRow,
    PortableDropbotPmtCaptureModel,
)


def test_merge_spots_builds_rows_in_slot_order_with_defaults():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(3, 24500), (1, 1000)])
    assert [
        (r.slot, r.position_um, r.capture, r.gain, r.exposure_s) for r in m.rows
    ] == [
        (1, 1000, True, DEFAULT_PMT_GAIN, DEFAULT_PMT_EXPOSURE_S),
        (3, 24500, True, DEFAULT_PMT_GAIN, DEFAULT_PMT_EXPOSURE_S),
    ]
    assert m.rows[1].label == "Spot 3 · 24.50 mm"


def test_merge_spots_keeps_settings_order_and_refreshes_positions():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000), (2, 2000), (3, 3000)])
    m.rows[0].capture = False
    m.rows[2].gain = 200
    m.rows = [m.rows[2], m.rows[0], m.rows[1]]  # operator reordered
    m.merge_spots([(1, 1111), (3, 3000), (4, 4000)])  # slot 2 gone, 4 new
    assert [r.slot for r in m.rows] == [3, 1, 4]
    assert m.rows[0].gain == 200
    assert m.rows[1].capture is False and m.rows[1].position_um == 1111
    assert m.rows[2].gain == DEFAULT_PMT_GAIN


def test_merge_spots_empty_clears_rows():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000), (2, 2000)])
    m.merge_spots([])
    assert m.rows == []


def test_capture_entries_honours_ticks_and_order():
    m = PortableDropbotPmtCaptureModel()
    m.rows = [
        PmtSpotRow(slot=2, position_um=0, gain=90, exposure_s=1.5),
        PmtSpotRow(slot=1, position_um=0, capture=False),
        PmtSpotRow(slot=5, position_um=0, gain=10, exposure_s=2.5),
    ]
    assert m.capture_entries() == [
        {"slot": 2, "gain": 90, "exposure_s": 1.5},
        {"slot": 5, "gain": 10, "exposure_s": 2.5},
    ]
