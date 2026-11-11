# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The device viewer carries no gamepad code after the move to its plugin."""

# Standard library imports.
import importlib.util

# Microdrop package imports.
import device_viewer.consts as device_viewer_consts
from device_viewer.preferences import DeviceViewerPreferences


def test_the_gamepad_service_is_gone():
    spec = importlib.util.find_spec(
        "device_viewer.services.gamepad_interaction_service"
    )

    assert spec is None


def test_no_gamepad_topics_or_defaults_remain():
    topics = [
        topic
        for subscribed in device_viewer_consts.ACTOR_TOPIC_DICT.values()
        for topic in subscribed
    ]

    assert not [topic for topic in topics if "gamepad" in topic]

    for name in (
        "GAMEPAD_CAPTURE_REQUEST",
        "GAMEPAD_RECONNECT_REQUEST",
        "GAMEPAD_BTN_CLEAR",
        "GAMEPAD_POLL_INTERVAL_MS",
    ):
        assert not hasattr(device_viewer_consts, name)


def test_the_device_viewer_preferences_hold_no_gamepad_settings():
    names = DeviceViewerPreferences.class_traits()

    assert not [name for name in names if "gamepad" in name]
