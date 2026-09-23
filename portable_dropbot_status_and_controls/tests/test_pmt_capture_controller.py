# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> topics for the PMT Capture pane. The validated publishers and
publish_message are patched; no Redis."""

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    MOTOR_HOME,
    PMT_CAPTURE_ABORT,
    PMT_MOVE_TO_SPOT,
    PMT_SPOTS_READ,
    PMT_STREAM_STOP,
)
from portable_dropbot_protocol_controls.consts import PMT_CAPTURE_COLUMN_ID
from portable_dropbot_status_and_controls.controllers import (
    pmt_capture_controller as mod,
)
from portable_dropbot_status_and_controls.controllers.pmt_capture_controller import (
    PmtCaptureController,
)
from portable_dropbot_status_and_controls.models.capture_pane_model import (
    CaptureResultFrame,
)
from portable_dropbot_status_and_controls.models.pmt_capture_model import (
    PmtSpotResultRow,
    PmtSpotRow,
    PortableDropbotPmtCaptureModel,
)


def _wire(monkeypatch):
    sent = {"capture": [], "stream": [], "acquire": [], "raw": [], "set_cell": []}
    monkeypatch.setattr(
        mod.pmt_capture_publisher, "publish", lambda p, **k: sent["capture"].append(p)
    )
    monkeypatch.setattr(
        mod.pmt_stream_start_publisher,
        "publish",
        lambda p, **k: sent["stream"].append(p),
    )
    monkeypatch.setattr(
        mod.pmt_acquire_publisher, "publish", lambda p, **k: sent["acquire"].append(p)
    )
    monkeypatch.setattr(
        mod,
        "publish_message",
        lambda topic, message: sent["raw"].append((topic, message)),
    )
    monkeypatch.setattr(
        mod.protocol_tree_set_cell_publisher,
        "publish",
        lambda **kw: sent["set_cell"].append(kw),
    )
    model = PortableDropbotPmtCaptureModel()
    return model, PmtCaptureController(model), sent


def test_start_publishes_ticked_entries_and_stream_settings(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [PmtSpotRow(slot=2, position_um=0, gain=90, exposure_s=1.5)]
    model.stream_avg = 32
    model.start_button = True

    assert len(sent["capture"]) == 1
    payload = sent["capture"][0]
    assert payload["entries"] == [{"slot": 2, "gain": 90, "exposure_s": 1.5}]
    assert payload["avg"] == 32
    assert payload["osr"] == model.stream_osr
    assert payload["rf_ohms"] == model.rf_ohms
    assert payload["park_motor"] is False
    assert payload["request_id"]  # a fresh uuid4, non-empty
    # The model follows the request it just minted.
    assert model.capture_request_id == payload["request_id"]
    assert model.capturing is True


def test_start_with_nothing_ticked_publishes_nothing(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [PmtSpotRow(slot=2, position_um=0, capture=False)]
    model.start_button = True
    assert sent["capture"] == [] and model.capturing is False
    assert model.progress == "No spot ticked"


def test_abort_and_refresh_topics(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.abort_button = True
    model.refresh_button = True
    assert sent["raw"] == [(PMT_CAPTURE_ABORT, ""), (PMT_SPOTS_READ, "")]


def test_live_spot_change_publishes_move_to_spot(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.live_spot = 3
    assert sent["raw"] == [(PMT_MOVE_TO_SPOT, "3")]


def test_home_pmt_publishes_motor_home_only_and_resets_live_spot(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.live_spot = 2
    sent["raw"].clear()

    model.home_pmt_button = True

    assert sent["raw"] == [(MOTOR_HOME, "pmt")]
    assert model.live_spot == 0


def test_stream_start_clears_live_data_and_publishes_request(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.append_live([1, 2, 3], packets=1)
    model.gain = 200
    model.stream_start_button = True
    assert len(model.live_counts) == 0 and model.live_packets == 0
    assert sent["stream"] == [model.stream_request()]


def test_stream_stop_publishes_the_stop_topic(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.stream_stop_button = True
    assert sent["raw"] == [(PMT_STREAM_STOP, "")]


def test_avg_osr_gain_republish_only_while_streaming(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.stream_avg = 32  # not streaming yet: no republish
    assert sent["stream"] == []

    model.streaming = True
    model.stream_osr = 4
    model.gain = 50
    assert len(sent["stream"]) == 2
    assert sent["stream"][-1] == model.stream_request()


def test_acquire_sets_state_and_publishes_request(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.gain = 128
    model.acquire_button = True
    assert model.acquiring is True
    assert model.acquire_summary == "acquiring (~20 s)..."
    assert sent["acquire"] == [model.acquire_request()]


def test_attached_edit_publishes_set_cell(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [PmtSpotRow(slot=1, position_um=0, at_start=True)]
    model.attached_step_id = "step-1"

    model.rows[0].gain = 200

    assert len(sent["set_cell"]) == 1
    assert sent["set_cell"][0]["step_id"] == "step-1"
    assert sent["set_cell"][0]["col_id"] == PMT_CAPTURE_COLUMN_ID
    assert sent["set_cell"][0]["value"]["entries"][0]["gain"] == 200
    assert model.last_pushed_step_id == "step-1"
    assert model.last_pushed_value == sent["set_cell"][0]["value"]


def test_unattached_edit_publishes_nothing(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [PmtSpotRow(slot=1, position_um=0)]
    model.rows[0].gain = 200
    assert sent["set_cell"] == []


def test_attached_edit_during_a_run_publishes_nothing(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [PmtSpotRow(slot=1, position_um=0, at_start=True)]
    model.attached_step_id = "step-1"
    model.protocol_running = True

    model.rows[0].gain = 200

    assert sent["set_cell"] == []


def test_loading_a_step_does_not_push(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.merge_spots([(1, 1000)])

    model.attach_step(
        "step-1",
        {"entries": [{"slot": 1, "gain": 90, "exposure_s": 1.0, "at_end": True}]},
    )

    assert sent["set_cell"] == []


def test_file_link_opens_the_rows_path_and_arrows_page_frames(monkeypatch):
    model, _controller, _sent = _wire(monkeypatch)
    opened = []
    monkeypatch.setattr(mod, "open_file", opened.append)

    first = CaptureResultFrame(rows=[PmtSpotResultRow(path="/tmp/a.csv")])
    second = CaptureResultFrame(rows=[PmtSpotResultRow(path="/tmp/b.csv")])
    model.result_frames = [first, second]
    model.frame_index = 1

    model.results[0].open_file = True
    assert opened == ["/tmp/b.csv"]

    model.previous_frame_button = True
    assert model.frame_index == 0
    assert model.results[0].path == "/tmp/a.csv"

    model.next_frame_button = True
    assert model.frame_index == 1
