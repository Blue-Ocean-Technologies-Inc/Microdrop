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
shape with the driver's liquid channels, judged against the threshold
preference, and a refused or empty scan is an error carrying the reason."""

# Standard library imports.
import json
from dataclasses import dataclass, field, replace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DROPLET_DETECTION_THRESHOLD_PF,
    DROPLET_DETECTION_THRESHOLD_PF_KEY,
    DROPLETS_DETECTED,
)
from portable_dropbot_controller.services import (
    portable_dropbot_droplet_detection_mixin_service as detection_service,
)

#: Capacitance (pF) per channel on the fake board: channel 1 holds liquid.
READINGS = {0: 1.0, 1: 25.0, 2: 3.0}

REFUSAL_REASON = "HV is off, the pads are not engaged (no device detected)"


@dataclass(frozen=True)
class _Thresholds:
    """The driver's immutable ChannelThresholds, reduced to with_default."""

    default_pf: float = 5.0
    per_channel: dict = field(default_factory=dict)

    def with_default(self, pf):
        return replace(self, default_pf=pf)


@dataclass(frozen=True)
class _Result:
    liquid: list
    readings: dict
    unmeasured: list = field(default_factory=list)

    def summary(self):
        return f"{len(self.liquid)} drop channel(s) found"


class _Refused(RuntimeError):
    """Stands in for the driver's FindDropsRefused, a RuntimeError."""

    def __init__(self, reason):
        super().__init__(f"find drops refused: {reason}")
        self.reason = reason


class _Session:
    """Records every find_drops call and judges READINGS against the
    thresholds it holds at that moment."""

    def __init__(self, readings=READINGS, refusal=None):
        self.calls = []
        self.readings = dict(readings)
        self.refusal = refusal
        self.drop_thresholds = _Thresholds(per_channel={7: 40.0})

    def find_drops(self, channels=None):
        self.calls.append((channels, self.drop_thresholds))

        if self.refusal:
            raise _Refused(self.refusal)

        liquid = sorted(
            channel
            for channel, capacitance in self.readings.items()
            if capacitance >= self.drop_thresholds.default_pf
        )

        return _Result(liquid=liquid, readings=dict(self.readings))


class _Base(HasTraits):
    proxy = Any()

    def _proxy_call(self, context, call):
        """The real _proxy_call's contract: the raised exception on failure."""
        try:
            return True, call()
        except Exception as error:
            return False, error


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


def test_detection_replies_with_the_drivers_liquid_channels(harness, detected):
    harness.on_detect_droplets_request("[0, 1, 2]")

    assert detected == [{"success": True, "detected_channels": [1], "error": ""}]
    assert harness.proxy.calls[0][0] == [0, 1, 2]


def test_empty_request_scans_the_sessions_used_channels(harness, detected):
    harness.on_detect_droplets_request("[]")

    assert harness.proxy.calls[0][0] is None


def test_dry_chip_reports_no_channels(detected):
    harness = _Harness(proxy=_Session({0: 1.0, 1: 2.0, 2: 3.0}))

    harness.on_detect_droplets_request("[]")

    assert detected == [{"success": True, "detected_channels": [], "error": ""}]


def test_threshold_defaults_to_5_pf_when_the_preference_is_unset(harness, detected):
    harness.on_detect_droplets_request("[]")

    _channels, thresholds = harness.proxy.calls[0]
    assert thresholds.default_pf == DROPLET_DETECTION_THRESHOLD_PF == 5.0


def test_threshold_preference_reaches_the_session(harness, detected):
    detection_service.app_globals[DROPLET_DETECTION_THRESHOLD_PF_KEY] = 30.0

    harness.on_detect_droplets_request("[]")

    _channels, thresholds = harness.proxy.calls[0]
    assert thresholds.default_pf == 30.0
    assert thresholds.per_channel == {7: 40.0}
    assert detected[0]["detected_channels"] == []


def test_refused_scan_replies_with_the_drivers_reason(detected):
    harness = _Harness(proxy=_Session(refusal=REFUSAL_REASON))

    harness.on_detect_droplets_request("[]")

    assert detected[0]["success"] is False
    assert REFUSAL_REASON in detected[0]["error"]


def test_scan_with_no_readings_replies_with_an_error(detected):
    harness = _Harness(proxy=_Session({}))

    harness.on_detect_droplets_request("[]")

    assert detected[0]["success"] is False
    assert detected[0]["error"] == detection_service.SCAN_FAILED_MESSAGE
