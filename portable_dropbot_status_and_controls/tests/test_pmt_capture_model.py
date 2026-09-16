# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The PMT Capture pane model's pure rules: merging a fresh spot list,
turning ticked rows into request payloads, the live-stream rolling window
and unit conversion, and adopting a capture's per-spot results."""

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DEFAULT_PMT_EXPOSURE_S,
    DEFAULT_PMT_GAIN,
    PmtCaptureDone,
    PmtSpotResult,
)
from portable_dropbot_status_and_controls.consts import PMT_LIVE_WINDOW_SAMPLES
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


def test_capture_request_carries_stream_settings():
    m = PortableDropbotPmtCaptureModel()
    m.rows = [PmtSpotRow(slot=1, position_um=0, gain=90, exposure_s=1.5)]
    m.stream_avg = 32
    m.stream_osr = 4
    m.rf_ohms = 250_000.0
    assert m.capture_request() == {
        "entries": [{"slot": 1, "gain": 90, "exposure_s": 1.5}],
        "avg": 32,
        "osr": 4,
        "rf_ohms": 250_000.0,
    }


def test_stream_request_and_acquire_request_use_shared_gain_and_rf():
    m = PortableDropbotPmtCaptureModel()
    m.gain = 200
    m.stream_avg = 16
    m.stream_osr = 6
    m.rf_ohms = 499_000.0
    assert m.stream_request() == {
        "gain": 200,
        "avg": 16,
        "osr": 6,
        "rf_ohms": 499_000.0,
    }
    assert m.acquire_request() == {"gain": 200, "rf_ohms": 499_000.0}


def test_append_live_trims_to_the_display_window():
    m = PortableDropbotPmtCaptureModel()
    m.append_live(list(range(PMT_LIVE_WINDOW_SAMPLES - 1)), packets=1)
    m.append_live([9999, 8888], packets=1)
    assert len(m.live_counts) == PMT_LIVE_WINDOW_SAMPLES
    assert list(m.live_counts[-2:]) == [9999, 8888]
    assert m.live_packets == 2


def test_clear_live_resets_window_and_packets():
    m = PortableDropbotPmtCaptureModel()
    m.append_live([1, 2, 3], packets=1)
    m.clear_live()
    assert len(m.live_counts) == 0
    assert m.live_packets == 0


def test_live_values_convert_counts_to_the_selected_unit():
    m = PortableDropbotPmtCaptureModel()
    m.adc_full_scale = 65536
    m.rf_ohms = 499_000.0
    m.append_live([32768], packets=1)

    m.live_units = "Counts"
    assert list(m.live_values) == [32768]

    m.live_units = "Volts"
    assert m.live_values[0] == m.counts_to_volts(32768, 65536)

    m.live_units = "Current"
    assert m.live_values[0] == m.counts_to_amps(32768, 65536, 499_000.0)


def test_set_results_converts_with_the_captures_own_scale():
    m = PortableDropbotPmtCaptureModel()
    # The pane's current settings differ from what the capture actually
    # used — set_results must use the payload's, not these.
    m.adc_full_scale = 4096
    m.rf_ohms = 1_000.0

    done = PmtCaptureDone(
        ok=True,
        aborted=False,
        directory="/tmp/pmt",
        results=[
            PmtSpotResult(
                slot=1,
                gain=128,
                exposure_s=10.0,
                n_samples=620,
                mean_counts=32768.0,
                sd_counts=10.0,
                min_counts=32000,
                max_counts=33000,
                csv_path="/tmp/pmt/spot1.csv",
            ),
            PmtSpotResult(
                slot=2,
                gain=128,
                exposure_s=10.0,
                n_samples=0,
                mean_counts=0.0,
                sd_counts=0.0,
                min_counts=0,
                max_counts=0,
                error="no stream frames received",
            ),
        ],
        adc_full_scale=65536,
        rf_ohms=499_000.0,
    )
    m.set_results(done)

    assert [r.file for r in m.results] == ["spot1.csv", ""]
    assert m.results[0].mean_current == m.format_current(
        m.counts_to_amps(32768.0, 65536, 499_000.0)
    )
    assert m.results[1].mean_current == "-"
    assert m.results[1].error == "no stream frames received"
