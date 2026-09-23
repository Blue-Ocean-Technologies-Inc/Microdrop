# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The PMT Capture pane's message handler: the ADC full-scale rule (keep
the previous value when a query answers "unknown"), that disconnecting
cannot leave streaming/acquiring stuck True in the UI, and the "pane
follows step" row-selected attach/detach with its echo suppression."""

# Standard library imports.
import time

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeRowSelectedMessage
from portable_dropbot_controller.consts import (
    PmtAdcUpdated,
    PmtCaptureDone,
    PmtCaptureProgress,
)
from portable_dropbot_protocol_controls.consts import PMT_CAPTURE_COLUMN_ID
from portable_dropbot_status_and_controls.message_handlers import (
    pmt_capture_message_handler as mod,
)
from portable_dropbot_status_and_controls.models.pmt_capture_model import (
    PortableDropbotPmtCaptureModel,
)

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import TimestampedMessage


@pytest.fixture
def handler(request):
    model = PortableDropbotPmtCaptureModel()
    h = mod.PortableDropbotPmtCaptureMessageHandler(
        model=model, name=f"test_{request.node.name}"
    )
    yield h
    h.teardown()


def test_adc_update_adopts_full_scale_when_known(handler):
    handler._on_pmt_adc_updated_triggered(
        PmtAdcUpdated(
            adc_type=2, name="ADS7076 (16-bit)", full_scale=65536
        ).model_dump_json()
    )
    assert handler.model.adc_full_scale == 65536
    assert handler.model.adc_display == "ADS7076 (16-bit)"


def test_adc_update_keeps_previous_full_scale_when_unknown(handler):
    handler.model.adc_full_scale = 65536
    handler._on_pmt_adc_updated_triggered(
        PmtAdcUpdated(
            adc_type=0, name="unknown", full_scale=0, error="query failed"
        ).model_dump_json()
    )
    assert handler.model.adc_full_scale == 65536
    assert handler.model.adc_display == "query failed"


def test_disconnect_clears_streaming_and_acquiring(handler):
    handler.model.streaming = True
    handler.model.acquiring = True
    handler._on_disconnected_triggered(TimestampedMessage("", time.time() * 1000))
    assert handler.model.connected is False
    assert handler.model.streaming is False
    assert handler.model.acquiring is False


def test_capture_done_populates_results(handler):
    handler.model.capture_request_id = "r1"
    handler._on_pmt_capture_done_triggered(
        PmtCaptureDone(
            ok=True, aborted=False, directory="/tmp/pmt", results=[], request_id="r1"
        ).model_dump_json()
    )
    assert handler.model.results == []
    assert handler.model.capturing is False
    assert handler.model.capture_request_id == ""


def test_capture_progress_for_own_request_highlights_the_active_row(handler):
    handler.model.merge_spots([(1, 1000), (2, 2000)])
    handler.model.capture_request_id = "r1"

    handler._on_pmt_capture_progress_triggered(
        PmtCaptureProgress(
            index=0, total=2, slot=2, stage="gain", request_id="r1"
        ).model_dump_json()
    )

    assert handler.model.capturing is True
    assert [r.active for r in handler.model.rows] == [False, True]
    assert handler.model.progress == "Spot 2 (1/2): gain"


def test_capture_progress_for_a_foreign_request_id_is_ignored(handler):
    handler.model.merge_spots([(1, 1000)])
    handler.model.capture_request_id = "own"

    handler._on_pmt_capture_progress_triggered(
        PmtCaptureProgress(
            index=0,
            total=1,
            slot=1,
            stage="stream",
            exposure_s=5.0,
            request_id="step-1:start",
        ).model_dump_json()
    )

    assert handler.model.capturing is False
    assert all(not r.active for r in handler.model.rows)
    assert handler.model.progress == "-"
    assert handler.model.exposure_deadline == 0.0


def test_capture_done_for_a_foreign_request_id_leaves_the_pane_untouched(handler):
    handler.model.merge_spots([(1, 1000)])
    handler.model.mark_active_row(1)
    handler.model.capturing = True
    handler.model.capture_request_id = "own"

    handler._on_pmt_capture_done_triggered(
        PmtCaptureDone(
            ok=True,
            aborted=False,
            directory="/tmp/pmt",
            results=[],
            request_id="step-1:start",
        ).model_dump_json()
    )

    assert handler.model.capturing is True
    assert handler.model.rows[0].active is True
    assert handler.model.capture_request_id == "own"


def test_row_selected_with_step_id_attaches(handler):
    handler.model.merge_spots([(1, 1000)])
    cell = {
        "avg": 16,
        "osr": 6,
        "rf_ohms": 499_000.0,
        "entries": [{"slot": 1, "gain": 128, "exposure_s": 10.0, "at_start": True}],
    }
    msg = ProtocolTreeRowSelectedMessage(
        step_id="step-1", cells={PMT_CAPTURE_COLUMN_ID: cell}
    )
    handler._on_row_selected_triggered(msg.serialize())
    assert handler.model.attached_step_id == "step-1"
    assert handler.model.rows[0].at_start is True


def test_row_selected_without_step_id_detaches(handler):
    handler.model.merge_spots([(1, 1000)])
    handler.model.attach_step("step-1", None)
    msg = ProtocolTreeRowSelectedMessage(step_id=None)
    handler._on_row_selected_triggered(msg.serialize())
    assert handler.model.attached_step_id == ""


def test_row_selected_echo_of_own_push_is_ignored(handler):
    handler.model.merge_spots([(1, 1000)])
    handler.model.attach_step("step-1", None)
    pushed_value = {"avg": 16, "osr": 6, "rf_ohms": 499_000.0, "entries": []}
    handler.model.record_pushed_value(pushed_value)
    # A distinguishing mutation the echo must NOT clobber, since it should
    # be recognized as our own push and skipped rather than reapplied.
    handler.model.rows[0].gain = 200

    msg = ProtocolTreeRowSelectedMessage(
        step_id="step-1", cells={PMT_CAPTURE_COLUMN_ID: pushed_value}
    )
    handler._on_row_selected_triggered(msg.serialize())
    assert handler.model.rows[0].gain == 200


def test_row_selected_foreign_change_reloads(handler):
    handler.model.merge_spots([(1, 1000)])
    handler.model.attach_step("step-1", None)
    handler.model.record_pushed_value(
        {"avg": 16, "osr": 6, "rf_ohms": 499_000.0, "entries": []}
    )
    different = {
        "avg": 16,
        "osr": 6,
        "rf_ohms": 499_000.0,
        "entries": [{"slot": 1, "gain": 50, "exposure_s": 3.0, "at_end": True}],
    }
    msg = ProtocolTreeRowSelectedMessage(
        step_id="step-1", cells={PMT_CAPTURE_COLUMN_ID: different}
    )
    handler._on_row_selected_triggered(msg.serialize())
    assert handler.model.rows[0].gain == 50
    assert handler.model.rows[0].at_end is True
