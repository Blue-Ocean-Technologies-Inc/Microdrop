# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> topics for the Fluorescence Capture pane. The validated
publisher and publish_message are patched; no Redis."""

# Microdrop package imports.
from portable_dropbot_controller.consts import FLUORESCENCE_CAPTURE_ABORT
from portable_dropbot_protocol_controls.consts import FLUORESCENCE_CAPTURE_COLUMN_ID
from portable_dropbot_status_and_controls.controllers import (
    fluorescence_capture_controller as mod,
)
from portable_dropbot_status_and_controls.controllers.fluorescence_capture_controller import (  # noqa: E501
    FluorescenceCaptureController,
)
from portable_dropbot_status_and_controls.models.fluorescence_capture_model import (
    FluorescenceResultRow,
    FluorescenceRow,
    PortableDropbotFluorescenceCaptureModel,
)


def _wire(monkeypatch):
    sent = {"capture": [], "raw": [], "set_cell": []}
    monkeypatch.setattr(
        mod.fluorescence_capture_publisher,
        "publish",
        lambda p, **k: sent["capture"].append(p),
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
    model = PortableDropbotFluorescenceCaptureModel()
    return model, FluorescenceCaptureController(model), sent


def test_start_publishes_ticked_entries_with_a_fresh_request_id(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [FluorescenceRow(filter_position=2, led_percent=80, exposure_ms=25.0)]
    model.start_button = True

    assert len(sent["capture"]) == 1
    payload = sent["capture"][0]
    assert payload["entries"] == [
        {
            "filter_position": 2,
            "led_percent": 80,
            "exposure_ms": 25.0,
            "focus_distance": None,
        }
    ]
    assert payload["label"] == "manual"
    assert payload["request_id"]  # a fresh uuid4, non-empty
    assert model.running is True


def test_start_with_nothing_ticked_publishes_nothing(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [FluorescenceRow(filter_position=0, capture=False)]
    model.start_button = True
    assert sent["capture"] == [] and model.running is False
    assert model.status == "No filter ticked"


def test_abort_publishes_the_abort_topic(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.abort_button = True
    assert sent["raw"] == [(FLUORESCENCE_CAPTURE_ABORT, "")]


def test_attached_edit_publishes_set_cell(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [FluorescenceRow(filter_position=1, at_start=True)]
    model.attached_step_id = "step-1"

    model.rows[0].led_percent = 90

    assert len(sent["set_cell"]) == 1
    assert sent["set_cell"][0]["step_id"] == "step-1"
    assert sent["set_cell"][0]["col_id"] == FLUORESCENCE_CAPTURE_COLUMN_ID
    assert sent["set_cell"][0]["value"]["entries"][0]["led_percent"] == 90
    assert model.last_pushed_step_id == "step-1"
    assert model.last_pushed_value == sent["set_cell"][0]["value"]


def test_unattached_edit_publishes_nothing(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [FluorescenceRow(filter_position=1)]
    model.rows[0].led_percent = 90
    assert sent["set_cell"] == []


def test_attached_edit_during_a_run_publishes_nothing(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [FluorescenceRow(filter_position=1, at_start=True)]
    model.attached_step_id = "step-1"
    model.protocol_running = True

    model.rows[0].led_percent = 90

    assert sent["set_cell"] == []


def test_loading_a_step_does_not_push(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.attach_step(
        "step-1",
        {
            "entries": [
                {
                    "filter_position": 0,
                    "led_percent": 90,
                    "exposure_ms": 1.0,
                    "at_end": True,
                }
            ]
        },
    )
    assert sent["set_cell"] == []


def test_file_link_opens_the_rows_path(monkeypatch):
    model, _controller, _sent = _wire(monkeypatch)
    opened = []
    monkeypatch.setattr(mod, "open_file", opened.append)

    model.result_rows = [FluorescenceResultRow(path="/tmp/flu/a.png", file="a.png")]
    model.result_rows[0].open_file = True

    assert opened == ["/tmp/flu/a.png"]
