# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the Device Viewer's Dramatiq listener controller: registration,
topic dispatch, and handlers acting on a stub pane (no Redis, no Qt)."""

# Standard library imports.
import json
from types import SimpleNamespace
from unittest.mock import patch

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.tasks.api import TraitsDockPane
from traits.api import Any, List

# Microdrop package imports.
from device_viewer.consts import (
    ACTOR_TOPIC_DICT,
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_CAMERA_SELECT_SOURCE,
    DISABLED_CHANNELS_CHANGED,
    PHASE_NAVIGATION_MODE,
    PROTOCOL_RUNNING,
    REALTIME_MODE_UPDATED,
    listener_name,
)

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import TimestampedMessage

CONTROLLER_MODULE = "device_viewer.controllers.device_viewer_message_controller"


class _StubPane(TraitsDockPane):
    """Just the pane surface the handlers touch."""

    model = Any()
    device_view = Any()
    device_viewer_advanced_preferences = Any()
    camera_control_widget = Any()

    #: Values passed to apply_phase_navigation_mode, in call order.
    applied_phase_navigation_modes = List()

    def apply_phase_navigation_mode(self, enabled):
        self.applied_phase_navigation_modes.append(enabled)


@pytest.fixture
def controller_and_actor_factory():
    """A controller over a stub pane, with actor registration patched out."""
    from device_viewer.controllers.device_viewer_message_controller import (
        DeviceViewerMessageController,
    )

    pane = _StubPane(
        model=SimpleNamespace(
            realtime_mode=False,
            electrodes=SimpleNamespace(disabled_channels=set()),
        ),
        device_viewer_advanced_preferences=SimpleNamespace(
            allow_hardware_disables=True
        ),
    )

    # The real factory also returns None when the name is already registered.
    with patch(
        f"{CONTROLLER_MODULE}.generate_class_method_dramatiq_listener_actor",
        return_value=None,
    ) as actor_factory:
        controller = DeviceViewerMessageController(pane=pane)

    return controller, actor_factory


def _dispatch(controller, topic, body):
    controller.listener_actor_routine(TimestampedMessage(body, 0), topic)


def test_registers_the_listener_under_the_consts_name(controller_and_actor_factory):
    controller, actor_factory = controller_and_actor_factory

    actor_factory.assert_called_once_with(
        listener_name=listener_name,
        class_method=controller.listener_actor_routine,
    )
    assert controller.listener_name == listener_name


def test_every_subscribed_topic_has_a_controller_handler():
    from device_viewer.controllers.device_viewer_message_controller import (
        DeviceViewerMessageController,
    )

    missing = [
        topic
        for topic in ACTOR_TOPIC_DICT[listener_name]
        if not callable(
            getattr(
                DeviceViewerMessageController,
                f"_on_{topic.split('/')[-1]}_triggered",
                None,
            )
        )
    ]

    assert missing == []


def test_realtime_topic_dispatches_to_the_model(controller_and_actor_factory):
    controller, _ = controller_and_actor_factory

    _dispatch(controller, REALTIME_MODE_UPDATED, "True")

    assert controller.pane.model.realtime_mode is True


def test_disabled_channels_update_the_electrodes(controller_and_actor_factory):
    controller, _ = controller_and_actor_factory

    _dispatch(controller, DISABLED_CHANNELS_CHANGED, json.dumps({"channels": [3, 5]}))

    assert controller.pane.model.electrodes.disabled_channels == {3, 5}


def test_phase_navigation_mode_is_marshalled_to_the_gui_thread(
    controller_and_actor_factory,
):
    controller, _ = controller_and_actor_factory

    with patch(f"{CONTROLLER_MODULE}.GUI") as gui:
        _dispatch(controller, PHASE_NAVIGATION_MODE, "true")

    gui.invoke_later.assert_called_once()
    callback, enabled = gui.invoke_later.call_args.args

    assert controller.pane.applied_phase_navigation_modes == []

    callback(enabled)

    assert controller.pane.applied_phase_navigation_modes == [True]


def test_handler_error_is_logged_not_raised(controller_and_actor_factory):
    controller, _ = controller_and_actor_factory

    # A raising handler must be logged by the dispatch routine, not propagate
    # out of the Dramatiq actor (that would stall the consumer).
    with patch("microdrop_utils.dramatiq_controller_base.logger") as dispatch_logger:
        _dispatch(controller, DISABLED_CHANNELS_CHANGED, "not json")

    dispatch_logger.error.assert_called()


# --------------------------------------------------------------------------- #
# Camera select_source requests                                                #
# --------------------------------------------------------------------------- #
class _StubSignal:
    def __init__(self):
        self.emitted = []

    def emit(self, payload):
        self.emitted.append(payload)


@pytest.fixture
def camera_widget():
    return SimpleNamespace(
        camera_model=SimpleNamespace(camera_active=True, camera_leased=False),
        camera_select_source_signal=_StubSignal(),
        camera_active_signal=_StubSignal(),
    )


@pytest.fixture
def select_source_replies():
    with patch(f"{CONTROLLER_MODULE}.camera_source_selected_publisher") as publisher:
        yield publisher.publish


def test_select_source_request_is_handed_to_the_camera_widget(
    controller_and_actor_factory, camera_widget, select_source_replies
):
    controller, _ = controller_and_actor_factory
    controller.pane.camera_control_widget = camera_widget

    _dispatch(
        controller,
        DEVICE_VIEWER_CAMERA_SELECT_SOURCE,
        json.dumps({"label": "ASI: ZWO ASI183MM", "active": True, "request_id": "r1"}),
    )

    assert camera_widget.camera_select_source_signal.emitted == [
        {"label": "ASI: ZWO ASI183MM", "active": True, "request_id": "r1"}
    ]
    select_source_replies.assert_not_called()


@pytest.mark.parametrize(
    "body, request_id, label, error",
    [
        ("not json", "", "", "Expecting value"),
        (json.dumps({"request_id": "r2"}), "r2", "", "label: Field required"),
        (
            json.dumps({"label": "Cam A", "activ": True, "request_id": "r3"}),
            "r3",
            "Cam A",
            "activ: Extra inputs are not permitted",
        ),
    ],
)
def test_invalid_select_source_request_is_answered_not_ok(
    controller_and_actor_factory,
    camera_widget,
    select_source_replies,
    body,
    request_id,
    label,
    error,
):
    controller, _ = controller_and_actor_factory
    controller.pane.camera_control_widget = camera_widget

    _dispatch(controller, DEVICE_VIEWER_CAMERA_SELECT_SOURCE, body)

    (reply,), _ = select_source_replies.call_args

    assert camera_widget.camera_select_source_signal.emitted == []
    assert reply["request_id"] == request_id
    assert reply["label"] == label
    assert reply["ok"] is False
    assert error in reply["error"]
    assert reply["active"] is True


def test_select_source_without_a_camera_widget_is_answered_not_ok(
    controller_and_actor_factory, select_source_replies
):
    controller, _ = controller_and_actor_factory

    _dispatch(
        controller,
        DEVICE_VIEWER_CAMERA_SELECT_SOURCE,
        json.dumps({"label": "Cam A", "request_id": "r4"}),
    )

    select_source_replies.assert_called_once_with(
        {
            "request_id": "r4",
            "label": "Cam A",
            "ok": False,
            "error": "Device viewer camera is not available",
            "active": False,
        }
    )


# --------------------------------------------------------------------------- #
# Camera lease                                                                 #
# --------------------------------------------------------------------------- #
def _select(controller, active):
    _dispatch(
        controller,
        DEVICE_VIEWER_CAMERA_SELECT_SOURCE,
        json.dumps({"label": "ASI: ZWO ASI183MM", "active": active}),
    )


def test_leased_camera_ignores_camera_off_but_not_on(
    controller_and_actor_factory, camera_widget, select_source_replies
):
    controller, _ = controller_and_actor_factory
    controller.pane.camera_control_widget = camera_widget

    _select(controller, True)
    _dispatch(controller, DEVICE_VIEWER_CAMERA_ACTIVE, "false")
    _dispatch(controller, DEVICE_VIEWER_CAMERA_ACTIVE, "true")

    assert camera_widget.camera_model.camera_leased is True
    assert camera_widget.camera_active_signal.emitted == [True]


def test_next_select_source_releases_the_lease(
    controller_and_actor_factory, camera_widget, select_source_replies
):
    controller, _ = controller_and_actor_factory
    controller.pane.camera_control_widget = camera_widget

    _select(controller, True)
    _select(controller, None)
    _dispatch(controller, DEVICE_VIEWER_CAMERA_ACTIVE, "false")

    assert camera_widget.camera_model.camera_leased is False
    assert camera_widget.camera_active_signal.emitted == [False]


def test_protocol_end_releases_the_lease(
    controller_and_actor_factory, camera_widget, select_source_replies
):
    controller, _ = controller_and_actor_factory
    controller.pane.camera_control_widget = camera_widget

    _select(controller, True)
    _dispatch(controller, PROTOCOL_RUNNING, "True")

    assert camera_widget.camera_model.camera_leased is True

    _dispatch(controller, PROTOCOL_RUNNING, "False")
    _dispatch(controller, DEVICE_VIEWER_CAMERA_ACTIVE, "false")

    assert camera_widget.camera_model.camera_leased is False
    assert camera_widget.camera_active_signal.emitted == [False]
