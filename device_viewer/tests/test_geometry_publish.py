# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for DV-side DEVICE_VIEWER_GEOMETRY_CHANGED publishing."""

# Standard library imports.
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.consts import DEVICE_VIEWER_GEOMETRY_CHANGED
from device_viewer.models.messages import GeometryChangedMessage


@pytest.fixture
def fake_publish_controller():
    """A minimal stand-in for DeviceViewerPublishController carrying just
    the attributes the helper touches."""

    class _Electrode:
        def __init__(self, channel):
            self.channel = channel

    controller = MagicMock()
    controller._last_published_id_to_channel = None
    controller.model.electrodes.electrodes = {
        "e00": _Electrode(0),
        "e01": _Electrode(1),
        "e02": _Electrode(None),
    }
    return controller


def test_publishes_on_first_call(fake_publish_controller):
    from device_viewer.controllers.device_viewer_publish_controller import (
        DeviceViewerPublishController,
    )

    with patch(
        "device_viewer.controllers.device_viewer_publish_controller.publish_message"
    ) as send:
        DeviceViewerPublishController._publish_geometry_if_changed(
            fake_publish_controller
        )

    send.assert_called_once()
    args, kwargs = send.call_args
    assert kwargs["topic"] == DEVICE_VIEWER_GEOMETRY_CHANGED
    msg = GeometryChangedMessage.deserialize(kwargs["message"])
    assert msg.id_to_channel == {"e00": 0, "e01": 1, "e02": None}


def test_no_republish_when_unchanged(fake_publish_controller):
    from device_viewer.controllers.device_viewer_publish_controller import (
        DeviceViewerPublishController,
    )

    with patch(
        "device_viewer.controllers.device_viewer_publish_controller.publish_message"
    ) as send:
        DeviceViewerPublishController._publish_geometry_if_changed(
            fake_publish_controller
        )
        DeviceViewerPublishController._publish_geometry_if_changed(
            fake_publish_controller
        )
    assert send.call_count == 1


def test_republishes_when_mapping_changes(fake_publish_controller):
    from device_viewer.controllers.device_viewer_publish_controller import (
        DeviceViewerPublishController,
    )

    with patch(
        "device_viewer.controllers.device_viewer_publish_controller.publish_message"
    ) as send:
        DeviceViewerPublishController._publish_geometry_if_changed(
            fake_publish_controller
        )
        # Simulate chip insert: mapping changes
        fake_publish_controller.model.electrodes.electrodes["e00"].channel = 5
        DeviceViewerPublishController._publish_geometry_if_changed(
            fake_publish_controller
        )
    assert send.call_count == 2
