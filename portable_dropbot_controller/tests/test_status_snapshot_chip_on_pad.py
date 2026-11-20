# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The signal board reports chip_on_pad as a 3-bit contact mask (debounced
presence, left pogo, right pogo); under the default presence rule (the
vendor's) the status snapshot publishes a chip whenever the debounced bit is
set, and the raw mask rides along as chip_pad_contacts. The driver's
readings are already in engineering units, so the snapshot publishes them
unscaled; hv_state bit3 adds the halt flag, and the driver's STATUS tail
adds the board's HV setpoint and faults. Hardware-free, no Redis."""

# Standard library imports.
import json
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Dict

# Microdrop package imports.
from portable_dropbot_controller import portable_dropbot_controller_base
from portable_dropbot_controller.consts import DEFAULT_CHIP_DETECT_RULE
from portable_dropbot_controller.portable_dropbot_controller_base import (
    PortableDropbotControllerBase,
)


class _Harness(PortableDropbotControllerBase):
    #: What the driver's status read answers.
    status = Dict()
    #: Stands in for PortableDropbotPreferences, whose defaults read Redis.
    preferences = Any(SimpleNamespace(chip_detect_rule=DEFAULT_CHIP_DETECT_RULE))

    def traits_init(self):
        pass

    def _proxy_call(self, context, call):
        return True, self.status

    def _publish_motors(self, mechanisms=None, poll=True):
        pass


@pytest.mark.parametrize(
    ("chip_on_pad", "expected"),
    [(0, False), (1, True), (3, True), (5, True), (6, False), (7, True)],
)
def test_chip_on_pad_follows_the_debounced_bit(monkeypatch, chip_on_pad, expected):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )

    harness = _Harness()
    harness.status = {"signal": {"chip_on_pad": chip_on_pad}}

    harness._publish_status_snapshot()

    assert published == [{"chip_on_pad": expected, "chip_pad_contacts": chip_on_pad}]


def test_engineering_units_are_published_unscaled(monkeypatch):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )

    signal = {
        "hv_vol": 100.0,
        "cur_temp": 25.0,
        "target_temp": 37.0,
        "dev_temp": 31.5,
        "dev_hum": 42.0,
    }
    harness = _Harness()
    harness.status = {"signal": signal}

    harness._publish_status_snapshot()

    assert published == [signal]


@pytest.mark.parametrize(
    ("hv_state", "halted"), [(0, False), (0b0011, False), (0b1000, True)]
)
def test_hv_state_bit3_publishes_the_halt_latch(monkeypatch, hv_state, halted):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )

    harness = _Harness()
    harness.status = {"signal": {"hv_state": hv_state}}

    harness._publish_status_snapshot()

    assert published == [{"hv_state": hv_state, "halted": halted}]


def test_status_tail_rides_along_when_the_driver_captured_one(monkeypatch):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )

    tail = {
        "hv_setpoint": 120.0,
        "fault_flags": 2,
        "faults": ["output-current-exceeded"],
    }
    harness = _Harness()
    harness.proxy = SimpleNamespace(uart=SimpleNamespace(last_status_tail=tail))
    harness.status = {"signal": {"hv_vol": 119.5}}

    harness._publish_status_snapshot()

    assert published == [{"hv_vol": 119.5, **tail}]


def test_no_status_tail_on_firmware_without_one(monkeypatch):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )

    harness = _Harness()
    harness.proxy = SimpleNamespace(uart=SimpleNamespace(last_status_tail=None))
    harness.status = {"signal": {"hv_vol": 119.5}}

    harness._publish_status_snapshot()

    assert published == [{"hv_vol": 119.5}]
