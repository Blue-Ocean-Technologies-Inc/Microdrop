# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Fluorescence Capture pane's message handler: progress highlights the
row being captured (shared with every capture pane — see
capture_pane_message_handler.py), and a finished capture clears the
highlight, records the saved-to folder and adds a result frame only when
the request was not refused."""

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FluorescenceCapturedFrame,
    FluorescenceCaptureDone,
    FluorescenceCaptureProgress,
)
from portable_dropbot_status_and_controls.message_handlers import (
    fluorescence_capture_message_handler as mod,
)
from portable_dropbot_status_and_controls.models.fluorescence_capture_model import (
    FluorescenceRow,
    PortableDropbotFluorescenceCaptureModel,
)


@pytest.fixture
def handler(request):
    model = PortableDropbotFluorescenceCaptureModel()
    h = mod.PortableDropbotFluorescenceCaptureMessageHandler(
        model=model, name=f"test_{request.node.name}"
    )
    yield h
    h.teardown()


def test_progress_highlights_the_active_row_and_sets_the_stage(handler):
    handler.model.rows = [
        FluorescenceRow(filter_position=1),
        FluorescenceRow(filter_position=2),
    ]

    handler._on_fluorescence_capture_progress_triggered(
        FluorescenceCaptureProgress(
            request_id="r1", index=0, total=2, filter_position=2, stage="camera"
        ).model_dump_json()
    )

    assert handler.model.capturing is True
    assert [r.active for r in handler.model.rows] == [False, True]
    assert handler.model.progress == "Filter 2 (1/2): camera"


def test_done_clears_highlight_and_adds_a_result_frame(handler):
    handler.model.rows = [FluorescenceRow(filter_position=1)]
    handler.model.mark_active_row(1)

    handler._on_fluorescence_capture_done_triggered(
        FluorescenceCaptureDone(
            request_id="r1",
            ok=True,
            label="manual",
            directory="/tmp/flu",
            frames=[
                FluorescenceCapturedFrame(filter_position=1, path="/tmp/flu/a.png")
            ],
        ).model_dump_json()
    )

    assert handler.model.capturing is False
    assert all(not r.active for r in handler.model.rows)
    assert handler.model.results_directory == "/tmp/flu"
    assert [r.path for r in handler.model.results] == ["/tmp/flu/a.png"]
    assert handler.model.progress == "1 frame(s) saved"


def test_done_refused_does_not_touch_directory_or_results(handler):
    handler._on_fluorescence_capture_done_triggered(
        FluorescenceCaptureDone(
            request_id="r1", ok=False, directory="", frames=[], error="busy"
        ).model_dump_json()
    )

    assert handler.model.results_directory == ""
    assert handler.model.result_frames == []
    assert handler.model.progress == "FAILED: busy"
