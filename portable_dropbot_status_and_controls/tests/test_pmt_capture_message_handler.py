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
the previous value when a query answers "unknown"), and that disconnecting
cannot leave streaming/acquiring stuck True in the UI."""

# Standard library imports.
import time

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    PmtAdcUpdated,
    PmtCaptureDone,
)
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
    handler._on_pmt_capture_done_triggered(
        PmtCaptureDone(
            ok=True, aborted=False, directory="/tmp/pmt", results=[]
        ).model_dump_json()
    )
    assert handler.model.results == []
    assert handler.model.capturing is False
