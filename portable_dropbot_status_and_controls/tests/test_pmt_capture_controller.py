# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> topics for the PMT Capture pane. The validated publisher and
publish_message are patched; no Redis."""

# Microdrop package imports.
from portable_dropbot_controller.consts import PMT_CAPTURE_ABORT, PMT_SPOTS_READ
from portable_dropbot_status_and_controls.controllers import (
    pmt_capture_controller as mod,
)
from portable_dropbot_status_and_controls.controllers.pmt_capture_controller import (
    PmtCaptureController,
)
from portable_dropbot_status_and_controls.models.pmt_capture_model import (
    PmtSpotRow,
    PortableDropbotPmtCaptureModel,
)


def _wire(monkeypatch):
    sent = {"capture": [], "raw": []}
    monkeypatch.setattr(
        mod.pmt_capture_publisher, "publish", lambda p, **k: sent["capture"].append(p)
    )
    monkeypatch.setattr(
        mod,
        "publish_message",
        lambda topic, message: sent["raw"].append((topic, message)),
    )
    model = PortableDropbotPmtCaptureModel()
    return model, PmtCaptureController(model), sent


def test_start_publishes_ticked_entries_and_marks_capturing(monkeypatch):
    model, _controller, sent = _wire(monkeypatch)
    model.rows = [PmtSpotRow(slot=2, position_um=0, gain=90, exposure_s=1.5)]
    model.start_button = True
    assert sent["capture"] == [
        {"entries": [{"slot": 2, "gain": 90, "exposure_s": 1.5}]}
    ]
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
