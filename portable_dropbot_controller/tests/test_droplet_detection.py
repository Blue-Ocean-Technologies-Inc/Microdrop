# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Droplet detection: the baseline request reports its channel count,
detection answers DETECT_DROPLETS in the DropBot's reply shape (or an error
without a baseline), and every scan puts the user's actuation back."""

# Standard library imports.
import json
import threading

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DROPLETS_DETECTED,
    LAST_CHANNEL_STATES_REQUESTED_KEY,
    DropletBaselineUpdated,
)
from portable_dropbot_controller.services import (
    portable_dropbot_droplet_detection_mixin_service as detection_service,
)

#: Dry-chip capacitance (pF) per channel on the fake board.
BASELINE = {0: 10, 1: 10, 2: 10}


class _Sig:
    def __init__(self, calls):
        self.calls = calls

    def hv_enable(self, on, bypass):
        self.calls.append(("hv_enable", on))

        return True


class _Session:
    """Records every call; channel 1 holds liquid."""

    def __init__(self):
        self.calls = []
        self.sig = _Sig(self.calls)

    def calibrate_baseline(self, switch_time_ms):
        self.calls.append("calibrate_baseline")

        return dict(BASELINE)

    def detect_drops(self, channels, threshold_pf, switch_time_ms):
        self.calls.append(("detect_drops", channels))
        scanned = channels or list(BASELINE)

        return {channel: channel == 1 for channel in scanned}

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


class _Publisher:
    def __init__(self):
        self.published = []

    def publish(self, payload):
        self.published.append(DropletBaselineUpdated.model_validate(payload))


@pytest.fixture
def replies(monkeypatch):
    """The baseline updates and DROPLETS_DETECTED replies, in order."""
    baseline_publisher = _Publisher()
    detected = []

    def publish_message(topic, message):
        assert topic == DROPLETS_DETECTED
        detected.append(json.loads(message))

    monkeypatch.setattr(
        detection_service, "droplet_baseline_updated_publisher", baseline_publisher
    )
    monkeypatch.setattr(detection_service, "publish_message", publish_message)
    monkeypatch.setattr(detection_service, "app_globals", {})

    return baseline_publisher.published, detected


@pytest.fixture
def harness():
    return _Harness(proxy=_Session())


def test_detection_without_baseline_replies_with_an_error(harness, replies):
    _, detected = replies

    harness.on_detect_droplets_request("[]")

    assert detected[0]["success"] is False
    assert "baseline" in detected[0]["error"]
    assert harness.proxy.calls == []


def test_baseline_reports_its_channel_count(harness, replies):
    baselines, _ = replies

    harness.on_calibrate_droplet_baseline_request("{}")

    assert baselines == [DropletBaselineUpdated(channels=len(BASELINE))]


def test_detection_replies_with_channels_holding_liquid(harness, replies):
    _, detected = replies
    harness.on_calibrate_droplet_baseline_request("{}")

    harness.on_detect_droplets_request("[0, 1]")

    assert detected == [{"success": True, "detected_channels": [1], "error": ""}]
    assert ("detect_drops", [0, 1]) in harness.proxy.calls


def test_empty_request_scans_every_channel(harness, replies):
    harness.on_calibrate_droplet_baseline_request("{}")

    harness.on_detect_droplets_request("[]")

    assert ("detect_drops", None) in harness.proxy.calls


def test_reconnect_discards_the_baseline(harness, replies):
    _, detected = replies
    harness.on_calibrate_droplet_baseline_request("{}")

    harness.proxy = _Session()
    harness.on_detect_droplets_request("[]")

    assert detected[0]["success"] is False


def test_scan_outside_realtime_leaves_electrodes_and_hv_off(harness, replies):
    harness.on_calibrate_droplet_baseline_request("{}")

    assert harness.proxy.calls[-3:] == [
        "apply_actuation",
        "clear_channels",
        ("hv_enable", 0),
    ]


def test_scan_in_realtime_restores_hv_and_the_last_electrodes(harness, replies):
    detection_service.app_globals[LAST_CHANNEL_STATES_REQUESTED_KEY] = json.dumps(
        {"channels": [2, 5]}
    )
    harness.realtime_mode = True

    harness.on_calibrate_droplet_baseline_request("{}")

    assert harness.proxy.calls[-3:] == [
        "apply_actuation",
        ("hv_enable", 1),
        ("actuate_channels", [2, 5]),
    ]
