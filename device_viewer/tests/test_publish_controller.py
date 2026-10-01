# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for DeviceViewerPublishController (#768): the outbound publishing
cluster moved off the dock pane. Runs against a real DeviceViewMainModel
(no Qt widgets, no Redis) with publish_message / electrode_state_change_
publisher patched.

``publish_message`` and the electrode publisher are patched for the whole
controller fixture, not just around each test's mutation: assigning
``model`` on construction fires every ``model.*`` observer once (the same
thing happens in production, at ``DeviceViewerDockPane.traits_init``'s
``self.model = DeviceViewMainModel(...)``), including the unconditional
``calibration_change_handler``. Patching only around the mutation under
test would let that first call reach the real (absent) Redis broker.
"""

# Standard library imports.
import json
from pathlib import Path
from unittest.mock import patch

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.undo.api import CommandStack, UndoManager

# Microdrop package imports.
from device_viewer.consts import (
    CALIBRATION_DATA,
    DEVICE_VIEWER_STATE_CHANGED,
    PHASE_NAVIGATION_MODE,
)
from device_viewer.controllers.device_viewer_publish_controller import (
    DeviceViewerPublishController,
)
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


@pytest.fixture
def model():
    undo_manager = UndoManager(active_stack=CommandStack())
    undo_manager.active_stack.undo_manager = undo_manager

    model = DeviceViewMainModel(
        undo_manager=undo_manager, preferences=DeviceViewerPreferences()
    )
    model.electrodes.set_electrodes_from_svg_file(str(BUNDLED_2X3))

    return model


@pytest.fixture
def send(model):
    """Patches publish_message for the controller's whole lifetime, so the
    construction-time firing of every ``model.*`` observer never reaches a
    real broker. Reset once construction's own calls (notably the
    unconditional calibration publish) are flushed, so each test only sees
    the calls its own action causes."""
    with patch(
        "device_viewer.controllers.device_viewer_publish_controller.publish_message"
    ) as mock:
        yield mock


@pytest.fixture
def electrode_publisher():
    with patch(
        "device_viewer.controllers.device_viewer_publish_controller."
        "electrode_state_change_publisher"
    ) as mock:
        yield mock


@pytest.fixture
def controller(model, send, electrode_publisher):
    controller = DeviceViewerPublishController(model=model)
    send.reset_mock()
    electrode_publisher.reset_mock()

    return controller


def test_state_message_published_on_model_change(controller, model, send):
    model.electrodes.actuated_channels = {0}

    assert controller.message_buffer
    topics = [kwargs["topic"] for _args, kwargs in send.call_args_list]
    assert DEVICE_VIEWER_STATE_CHANGED in topics


def test_disable_state_messages_gates_state_message(controller, model, send):
    baseline = controller.message_buffer
    controller._disable_state_messages = True

    model.electrodes.actuated_channels = {0}

    assert controller.message_buffer == baseline
    send.assert_not_called()


def test_disable_state_messages_gates_electrode_update(
    controller, model, electrode_publisher
):
    """The #434 echo guard: actuation applied FROM an inbound state message
    must not be re-published back to hardware."""
    model.realtime_mode = True
    model.connected = True
    model.free_mode = True
    # free_mode defaults True, so connected flipping true above already
    # satisfies the publish condition once, against the still-empty
    # channels — drop that setup echo before gating the real mutation.
    electrode_publisher.reset_mock()
    controller._disable_state_messages = True

    model.electrodes.actuated_channels = {0}

    electrode_publisher.publish.assert_not_called()


def test_electrode_update_published_in_free_mode(
    controller, model, electrode_publisher
):
    model.realtime_mode = True
    model.connected = True
    model.free_mode = True
    electrode_publisher.reset_mock()

    model.electrodes.actuated_channels = {0}

    electrode_publisher.publish.assert_called_once_with(
        model.electrodes.actuated_channels
    )


def test_phase_navigation_echo_guard(controller, model, send):
    """An inbound PHASE_NAVIGATION_MODE message sets
    _applying_phase_nav_message so the toggle isn't rebroadcast."""
    controller._applying_phase_nav_message = True

    model.phase_navigation_mode = True

    assert not any(
        kwargs.get("topic") == PHASE_NAVIGATION_MODE
        for _args, kwargs in send.call_args_list
    )


def test_phase_navigation_mode_published_when_user_toggles(controller, model, send):
    model.phase_navigation_mode = True

    send.assert_called_once_with(topic=PHASE_NAVIGATION_MODE, message="True")


def test_calibration_message_published_on_change(controller, model, send):
    model.liquid_capacitance_over_area = 5.0

    send.assert_called_once()
    _args, kwargs = send.call_args
    assert kwargs["topic"] == CALIBRATION_DATA
    payload = json.loads(kwargs["message"])
    assert payload["liquid_capacitance_over_area"] == 5.0
