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
from portable_dropbot_status_and_controls.consts import (
    PMT_EXPOSURE_RANGES,
    PMT_LIVE_WINDOW_SAMPLES,
)
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


def test_live_spot_labels_list_park_then_configured_spots_in_slot_order():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(3, 24500), (1, 1000)])
    assert m.live_spot_labels == {
        0: "0:Park (spot 0)",
        1: "1:Spot 1 · 1.00 mm",
        3: "3:Spot 3 · 24.50 mm",
    }


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
        "park_motor": False,
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


def test_add_result_frame_converts_with_the_captures_own_scale():
    m = PortableDropbotPmtCaptureModel()
    # The pane's current settings differ from what the capture actually
    # used — add_result_frame must use the payload's, not these.
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
    m.add_result_frame(done)

    assert [r.file for r in m.results] == ["spot1.csv", ""]
    assert m.results[0].path == "/tmp/pmt/spot1.csv"
    assert m.results[0].mean_voltage == m.format_quantity(
        m.counts_to_volts(32768.0, 65536), "V"
    )
    assert m.results[0].mean_current == m.format_quantity(
        m.counts_to_amps(32768.0, 65536, 499_000.0), "A"
    )
    assert m.results[1].mean_voltage == "-"
    assert m.results[1].mean_current == "-"
    assert m.results[1].error == "no stream frames received"


def test_add_result_frame_labels_with_the_dones_label():
    m = PortableDropbotPmtCaptureModel()
    m.add_result_frame(
        PmtCaptureDone(
            ok=True, aborted=False, directory="/tmp", results=[], label="step1.2-end"
        )
    )
    assert m.frame_label.startswith("Run 1 / 1 · ")
    assert m.frame_label.endswith("· step1.2-end")


def test_result_frames_page_through_runs_and_clamp_at_the_ends():
    m = PortableDropbotPmtCaptureModel()
    assert m.results == []
    assert m.frame_label == "no captures yet"

    for _ in range(2):
        m.add_result_frame(
            PmtCaptureDone(ok=True, aborted=False, directory="/tmp", results=[])
        )

    assert m.frame_index == 1
    assert m.frame_label.startswith("Run 2 / 2")
    assert m.has_previous_frame and not m.has_next_frame

    m.show_next_frame()
    assert m.frame_index == 1

    m.show_previous_frame()
    m.show_previous_frame()
    assert m.frame_index == 0
    assert not m.has_previous_frame and m.has_next_frame


def test_attach_step_loads_cell_order_gain_exposure_and_ticks():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000), (2, 2000), (3, 3000)])

    m.attach_step(
        "step-1",
        {
            "avg": 32,
            "osr": 4,
            "rf_ohms": 250_000.0,
            "entries": [
                {
                    "slot": 3,
                    "gain": 200,
                    "exposure_s": 5.0,
                    "at_start": True,
                    "at_end": False,
                },
                {
                    "slot": 1,
                    "gain": 90,
                    "exposure_s": 2.5,
                    "at_start": False,
                    "at_end": True,
                },
            ],
        },
    )

    assert m.attached_step_id == "step-1"
    assert m.attached_label == "Editing step step-1"
    assert [r.slot for r in m.rows] == [3, 1, 2]
    assert (m.rows[0].gain, m.rows[0].exposure_s) == (200, 5.0)
    assert m.rows[0].at_start is True and m.rows[0].at_end is False
    assert m.rows[1].at_start is False and m.rows[1].at_end is True
    # Slot 2 was absent from the cell: unticked, moved after.
    assert m.rows[2].at_start is False and m.rows[2].at_end is False
    assert (m.stream_avg, m.stream_osr, m.rf_ohms) == (32, 4, 250_000.0)


def test_attach_step_with_invalid_cell_reads_as_no_capture():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000)])
    m.attach_step("step-1", {"entries": [{"slot": 1}]})  # missing required fields
    assert m.attached_step_id == "step-1"
    assert m.rows[0].at_start is False and m.rows[0].at_end is False


def test_attach_step_with_no_cell_unticks_every_row():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000), (2, 2000)])
    m.rows[0].at_start = True
    m.attach_step("step-1", None)
    assert all(not r.at_start and not r.at_end for r in m.rows)


def test_detach_step_restores_the_manual_snapshot():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000), (2, 2000)])
    m.rows[0].capture = False
    m.rows[1].gain = 77
    m.stream_avg = 32
    original_order = [r.slot for r in m.rows]

    m.attach_step(
        "step-1",
        {"entries": [{"slot": 2, "gain": 5, "exposure_s": 1.0, "at_end": True}]},
    )
    assert m.attached_step_id == "step-1"

    m.detach_step()
    assert m.attached_step_id == ""
    assert m.attached_label == "Manual capture"
    assert [r.slot for r in m.rows] == original_order
    assert m.rows[0].capture is False
    assert m.rows[1].gain == 77
    assert m.stream_avg == 32
    assert all(not r.at_start and not r.at_end for r in m.rows)


def test_capture_request_and_step_cell_value_carry_park_motor():
    m = PortableDropbotPmtCaptureModel()
    m.park_motor = True
    m.rows = [PmtSpotRow(slot=1, position_um=0, at_start=True)]

    assert m.capture_request()["park_motor"] is True
    assert m.step_cell_value()["park_motor"] is True


def test_attach_step_loads_park_motor_and_detach_restores_the_manual_value():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000)])
    m.park_motor = True  # the manual value the snapshot must restore

    m.attach_step(
        "step-1",
        {
            "avg": 16,
            "osr": 6,
            "rf_ohms": 499_000.0,
            "park_motor": False,
            "entries": [{"slot": 1, "gain": 90, "exposure_s": 2.5, "at_start": True}],
        },
    )
    assert m.park_motor is False

    m.detach_step()
    assert m.park_motor is True


def test_step_cell_value_drops_unticked_and_returns_none_when_empty():
    m = PortableDropbotPmtCaptureModel()
    m.rows = [
        PmtSpotRow(slot=1, position_um=0, at_start=True),
        PmtSpotRow(slot=2, position_um=0),  # neither tick: dropped
    ]
    m.stream_avg = 16
    m.stream_osr = 6
    m.rf_ohms = 499_000.0
    assert m.step_cell_value() == {
        "avg": 16,
        "osr": 6,
        "rf_ohms": 499_000.0,
        "park_motor": False,
        "entries": [
            {
                "slot": 1,
                "gain": DEFAULT_PMT_GAIN,
                "exposure_s": DEFAULT_PMT_EXPOSURE_S,
                "at_start": True,
                "at_end": False,
            }
        ],
    }

    m.rows[0].at_start = False
    assert m.step_cell_value() is None


def test_capture_entries_uses_start_or_end_ticks_while_attached():
    m = PortableDropbotPmtCaptureModel()
    m.rows = [
        PmtSpotRow(slot=1, position_um=0, capture=False, at_start=True),
        PmtSpotRow(slot=2, position_um=0, capture=True),  # manual tick, no step tick
        PmtSpotRow(slot=3, position_um=0, at_end=True),
    ]
    m.attached_step_id = "step-1"
    assert [e["slot"] for e in m.capture_entries()] == [1, 3]


def test_exposure_range_sets_every_rows_slider_bound():
    m = PortableDropbotPmtCaptureModel()
    m.merge_spots([(1, 1000), (2, 2000)])
    assert {r.exposure_max for r in m.rows} == {PMT_EXPOSURE_RANGES[m.exposure_range]}

    m.exposure_range = "1–10 s"
    assert {r.exposure_max for r in m.rows} == {10.0}

    m.merge_spots([(1, 1000), (2, 2000), (3, 3000)])  # a new row follows too
    assert m.rows[2].exposure_max == 10.0
    # The pick never rewrites an exposure that is already above it.
    m.rows[0].exposure_s = 45.0
    m.exposure_range = "1–10 s"
    assert m.rows[0].exposure_s == 45.0


def test_exposure_countdown_appends_tenths_left_and_stops():
    m = PortableDropbotPmtCaptureModel()
    m.progress = "Spot 2 (1/3): stream"

    m.start_exposure_countdown(10.0, now=100.0)
    assert m.progress == "Spot 2 (1/3): stream · 10.0 s left"

    m.update_countdown(now=103.46)
    assert m.progress == "Spot 2 (1/3): stream · 6.5 s left"

    m.update_countdown(now=111.0)
    assert m.progress == "Spot 2 (1/3): stream · 0.0 s left"

    m.stop_countdown()
    m.update_countdown(now=112.0)
    assert m.exposure_deadline == 0.0
    assert m.progress == "Spot 2 (1/3): stream · 0.0 s left"
