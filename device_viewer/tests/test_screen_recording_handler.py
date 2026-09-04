# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the DV-side screen-recording handler's message parsing.

A malformed message on DEVICE_VIEWER_SCREEN_RECORDING must not raise out of
the dramatiq actor -- it stalls the consumer queue (#394)."""

# Standard library imports.
import json
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest


def _call_handler(message):
    """Run the handler against a stub pane, returning (pane, logger)."""
    from device_viewer.views.device_view_dock_pane import DeviceViewerDockPane

    pane = MagicMock()
    with patch("device_viewer.views.device_view_dock_pane.logger") as mock_logger:
        DeviceViewerDockPane._on_screen_recording_triggered(pane, message)
    return pane, mock_logger


def test_valid_message_emits_parsed_payload():
    payload = {"action": "start", "step_id": "uuid-abc"}
    pane, _ = _call_handler(json.dumps(payload))

    pane.camera_control_widget.screen_recording_signal.emit.assert_called_once_with(
        payload
    )


@pytest.mark.parametrize(
    "message", ["not json", '{"action": "start"', "{'action': 'start'}"]
)
def test_malformed_json_is_ignored_with_warning(message):
    pane, mock_logger = _call_handler(message)

    pane.camera_control_widget.screen_recording_signal.emit.assert_not_called()
    mock_logger.warning.assert_called_once()


@pytest.mark.parametrize("message", [None, "", "   "])
def test_empty_message_is_ignored_silently(message):
    pane, mock_logger = _call_handler(message)

    pane.camera_control_widget.screen_recording_signal.emit.assert_not_called()
    mock_logger.warning.assert_not_called()
