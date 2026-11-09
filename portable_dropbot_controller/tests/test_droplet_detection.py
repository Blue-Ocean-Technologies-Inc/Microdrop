# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Droplet detection: DETECT_DROPLETS is answered in the DropBot's reply
shape with the channels at or above the absolute threshold, a failed scan is
an error, and every scan puts the user's actuation back."""

# Standard library imports.
import json
import threading

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DROPLET_DETECTION_THRESHOLD_PF,
    DROPLETS_DETECTED,
    LAST_CHANNEL_STATES_REQUESTED_KEY,
)
from portable_dropbot_controller.services import (
    portable_dropbot_droplet_detection_mixin_service as detection_service,
)

#: Capacitance (pF) per channel on the fake board: channel 1 holds liquid,
#: channel 2 sits exactly on the threshold.
CAPACITANCES = {0: 3, 1: 25, 2: int(DROPLET_DETECTION_THRESHOLD_PF)}


class _Sig:
    def __init__(self, calls):
        self.calls = calls

    def hv_enable(self, on, bypass):
        self.calls.append(("hv_enable", on))

        return True


class _Session:
    """Records every call and reads back CAPACITANCES."""

    def __init__(self, capacitances=CAPACITANCES):
        self.calls = []
        self.sig = _Sig(self.calls)
        self.capacitances = dict(capacitances)

    def measure_capacitance(self, channels=None, switch_time_ms=20):
        self.calls.append(("measure_capacitance", channels))
        scanned = list(self.capacitances) if channels is None else channels

        return {
            channel: self.capacitances[channel]
            for channel in scanned
            if channel in self.capacitances
        }

    def clear_channels(self):
        self.calls.append("clear_channels")

    def actuate_channels(self, channels):
        self.calls.append(("actuate_channels", channels))


class _Base(HasTraits):
    proxy = Any()
    realtime_mode = Bool(False)
    _proxy_lock = Any(factory=threading.RLock)

    def _proxy_call(self, context, call):
        return True, call()

    def _apply_actuation(self):
        self.proxy.calls.append("apply_actuation")

    def _board_channels(self):
        return 120


class _Harness(detection_service.PortableDropbotDropletDetectionMixinService, _Base):
    pass


@pytest.fixture
def detected(monkeypatch):
    """The DROPLETS_DETECTED replies, in order."""
    replies = []

    def publish_message(topic, message):
        assert topic == DROPLETS_DETECTED
        replies.append(json.loads(message))

    monkeypatch.setattr(detection_service, "publish_message", publish_message)
    monkeypatch.setattr(detection_service, "app_globals", {})

    return replies


@pytest.fixture
def harness():
    return _Harness(proxy=_Session())


def test_detection_replies_with_channels_at_or_above_the_threshold(harness, detected):
    harness.on_detect_droplets_request("[0, 1, 2]")

    assert detected == [{"success": True, "detected_channels": [1, 2], "error": ""}]
    assert ("measure_capacitance", [0, 1, 2]) in harness.proxy.calls


def test_dry_chip_reports_no_channels(detected):
    harness = _Harness(proxy=_Session({0: 2, 1: 4, 2: 3}))

    harness.on_detect_droplets_request("[]")

    assert detected == [{"success": True, "detected_channels": [], "error": ""}]


def test_empty_request_scans_every_channel(harness, detected):
    harness.on_detect_droplets_request("[]")

    assert ("measure_capacitance", None) in harness.proxy.calls
    assert detected[0]["detected_channels"] == [1, 2]


def test_failed_scan_replies_with_an_error(detected):
    harness = _Harness(proxy=_Session({}))

    harness.on_detect_droplets_request("[]")

    assert detected[0]["success"] is False
    assert detected[0]["error"] == detection_service.SCAN_FAILED_MESSAGE


def test_scan_outside_realtime_leaves_electrodes_and_hv_off(harness, detected):
    harness.on_detect_droplets_request("[]")

    assert harness.proxy.calls[-3:] == [
        "apply_actuation",
        "clear_channels",
        ("hv_enable", 0),
    ]


def test_scan_in_realtime_restores_hv_and_the_last_electrodes(harness, detected):
    detection_service.app_globals[LAST_CHANNEL_STATES_REQUESTED_KEY] = json.dumps(
        {"channels": [2, 5]}
    )
    harness.realtime_mode = True

    harness.on_detect_droplets_request("[]")

    assert harness.proxy.calls[-3:] == [
        "apply_actuation",
        ("hv_enable", 1),
        ("actuate_channels", [2, 5]),
    ]
