# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Fluorescence Capture pane model's pure rules: the fixed filter-position
rows, ticked-row -> request payloads, the attach/detach/step-cell round trip
(copied from the PMT capture model, keyed by filter_position instead of
slot), and the results paged one capture run at a time."""

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FILTER_POSITIONS,
    FLUORESCENCE_DEFAULT_EXPOSURE_MS,
    FLUORESCENCE_DEFAULT_LED_PERCENT,
    FluorescenceCapturedFrame,
    FluorescenceCaptureDone,
)
from portable_dropbot_status_and_controls.models.fluorescence_capture_model import (
    FluorescenceRow,
    PortableDropbotFluorescenceCaptureModel,
)


def test_rows_default_to_one_per_filter_position_in_order():
    m = PortableDropbotFluorescenceCaptureModel()
    assert [r.filter_position for r in m.rows] == list(FILTER_POSITIONS)
    assert all(r.capture is True for r in m.rows)
    assert all(r.led_percent == FLUORESCENCE_DEFAULT_LED_PERCENT for r in m.rows)
    assert all(r.exposure_ms == FLUORESCENCE_DEFAULT_EXPOSURE_MS for r in m.rows)


def test_capture_entries_manual_mode_honours_ticks_and_leaves_focus_auto():
    m = PortableDropbotFluorescenceCaptureModel()
    m.rows = [
        FluorescenceRow(filter_position=2, led_percent=80, exposure_ms=25.0),
        FluorescenceRow(filter_position=1, capture=False),
        FluorescenceRow(filter_position=3, led_percent=10, exposure_ms=5.0),
    ]
    assert m.capture_entries() == [
        {
            "filter_position": 2,
            "led_percent": 80,
            "exposure_ms": 25.0,
            "focus_distance": None,
        },
        {
            "filter_position": 3,
            "led_percent": 10,
            "exposure_ms": 5.0,
            "focus_distance": None,
        },
    ]


def test_capture_entries_attached_mode_uses_start_or_end_ticks():
    m = PortableDropbotFluorescenceCaptureModel()
    m.rows = [
        FluorescenceRow(filter_position=1, capture=False, at_start=True),
        FluorescenceRow(filter_position=2, capture=True),  # manual tick, unused
        FluorescenceRow(filter_position=3, at_end=True),
    ]
    m.attached_step_id = "step-1"
    assert [e["filter_position"] for e in m.capture_entries()] == [1, 3]


def test_capture_request_wraps_entries_with_request_id_and_label():
    m = PortableDropbotFluorescenceCaptureModel()
    m.rows = [FluorescenceRow(filter_position=1, led_percent=50, exposure_ms=50.0)]
    assert m.capture_request(request_id="r1", label="manual") == {
        "entries": [
            {
                "filter_position": 1,
                "led_percent": 50,
                "exposure_ms": 50.0,
                "focus_distance": None,
            }
        ],
        "request_id": "r1",
        "label": "manual",
        "directory": "",
    }


def test_attach_step_loads_cell_order_settings_and_ticks():
    m = PortableDropbotFluorescenceCaptureModel()

    m.attach_step(
        "step-1",
        {
            "entries": [
                {
                    "filter_position": 3,
                    "led_percent": 90,
                    "exposure_ms": 12.5,
                    "focus_distance": 0.75,
                    "at_start": True,
                    "at_end": False,
                },
                {
                    "filter_position": 1,
                    "led_percent": 20,
                    "exposure_ms": 5.0,
                    "focus_distance": None,
                    "at_start": False,
                    "at_end": True,
                },
            ]
        },
    )

    assert m.attached_step_id == "step-1"
    assert m.attached_label == "Editing step step-1"
    assert [r.filter_position for r in m.rows] == [3, 1, 2, 4, 5]
    assert (m.rows[0].led_percent, m.rows[0].exposure_ms) == (90, 12.5)
    assert m.rows[0].at_start is True and m.rows[0].at_end is False
    assert m.rows[1].at_start is False and m.rows[1].at_end is True
    # Filter positions absent from the cell: unticked, moved after.
    assert all(not r.at_start and not r.at_end for r in m.rows[2:])


def test_attach_step_ignores_an_entry_naming_an_invalid_filter_position():
    m = PortableDropbotFluorescenceCaptureModel()
    m.attach_step(
        "step-1",
        {
            "entries": [
                {
                    "filter_position": 9,
                    "led_percent": 50,
                    "exposure_ms": 10.0,
                    "at_start": True,
                }
            ]
        },
    )
    assert all(not r.at_start and not r.at_end for r in m.rows)


def test_attach_step_with_invalid_cell_reads_as_no_capture():
    m = PortableDropbotFluorescenceCaptureModel()
    m.attach_step("step-1", {"entries": [{"filter_position": 1}]})  # missing fields
    assert m.attached_step_id == "step-1"
    assert all(not r.at_start and not r.at_end for r in m.rows)


def test_attach_step_with_no_cell_unticks_every_row():
    m = PortableDropbotFluorescenceCaptureModel()
    m.rows[0].at_start = True
    m.attach_step("step-1", None)
    assert all(not r.at_start for r in m.rows)


def test_detach_step_restores_the_manual_snapshot():
    m = PortableDropbotFluorescenceCaptureModel()
    m.rows[0].capture = False
    m.rows[1].led_percent = 77
    original_order = [r.filter_position for r in m.rows]

    m.attach_step(
        "step-1",
        {
            "entries": [
                {
                    "filter_position": m.rows[1].filter_position,
                    "led_percent": 5,
                    "exposure_ms": 1.0,
                    "at_end": True,
                }
            ]
        },
    )
    assert m.attached_step_id == "step-1"

    m.detach_step()
    assert m.attached_step_id == ""
    assert m.attached_label == "Manual capture"
    assert [r.filter_position for r in m.rows] == original_order
    assert m.rows[0].capture is False
    assert m.rows[1].led_percent == 77
    assert all(not r.at_start and not r.at_end for r in m.rows)


def test_step_cell_value_drops_unticked_and_returns_none_when_empty():
    m = PortableDropbotFluorescenceCaptureModel()
    m.rows = [
        FluorescenceRow(filter_position=1, at_start=True, led_percent=60),
        FluorescenceRow(filter_position=1),  # neither tick: dropped
    ]
    assert m.step_cell_value() == {
        "entries": [
            {
                "filter_position": 1,
                "led_percent": 60,
                "exposure_ms": m.rows[0].exposure_ms,
                "focus_distance": None,
                "at_start": True,
                "at_end": False,
            }
        ]
    }

    m.rows[0].at_start = False
    assert m.step_cell_value() is None


def test_record_pushed_value_remembers_step_and_value():
    m = PortableDropbotFluorescenceCaptureModel()
    m.attached_step_id = "step-1"
    m.record_pushed_value({"entries": []})
    assert m.last_pushed_step_id == "step-1"
    assert m.last_pushed_value == {"entries": []}


def test_add_result_frame_builds_rows_in_capture_order():
    m = PortableDropbotFluorescenceCaptureModel()
    done = FluorescenceCaptureDone(
        request_id="r1",
        ok=True,
        label="manual",
        directory="/tmp/flu",
        frames=[
            FluorescenceCapturedFrame(filter_position=2, path="/tmp/flu/b.png"),
            FluorescenceCapturedFrame(filter_position=4, path="/tmp/flu/c.png"),
        ],
    )

    m.add_result_frame(done)

    assert [r.filter_position for r in m.results] == [2, 4]
    assert [r.file for r in m.results] == ["b.png", "c.png"]
    assert m.results[0].path == "/tmp/flu/b.png"


def test_add_result_frame_pages_through_runs_with_the_dones_label():
    m = PortableDropbotFluorescenceCaptureModel()
    assert m.results == []
    assert m.frame_label == "no captures yet"

    for label in ("manual", "step1.2-end"):
        m.add_result_frame(
            FluorescenceCaptureDone(
                request_id="r",
                ok=True,
                label=label,
                directory="/tmp/flu",
                frames=[
                    FluorescenceCapturedFrame(filter_position=1, path="/tmp/flu/a.png")
                ],
            )
        )

    assert m.frame_index == 1
    assert m.frame_label.startswith("Run 2 / 2")
    assert m.frame_label.endswith("step1.2-end")
    assert m.has_previous_frame and not m.has_next_frame

    m.show_previous_frame()
    assert m.frame_index == 0
    assert m.frame_label.endswith("manual")
