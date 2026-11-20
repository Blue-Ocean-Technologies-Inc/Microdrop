# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""HV_ENABLE reply statuses judged the vendor's way: only "HV on" answers an
enable and "HV off" a disable; 2-5 are refusals reported as errors, never
logged as OK, and a refused enable takes realtime mode back off; leaving
realtime mode skips the proxy lock. Plus the halt-clear request.
Hardware-free, no Redis."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest
from dropbot_portable.halt_tool import HaltClear

# Enthought library imports.
from traits.api import Any, Bool, Dict, HasTraits, Int, List

# Microdrop package imports.
from portable_dropbot_controller.services.portable_dropbot_states_setting_mixin_service import (  # noqa: E501
    PortableDropbotStatesSettingMixinService,
)

decode = PortableDropbotStatesSettingMixinService._hv_enable_outcome


@pytest.mark.parametrize(
    ("enable", "status", "accepted"),
    [
        (True, 0, True),
        (False, 1, True),
        (True, 1, False),
        (True, 2, False),
        (True, 3, False),
        (True, 4, False),
        (True, 5, False),
        (True, None, False),
    ],
)
def test_hv_enable_status_decode(enable, status, accepted):
    assert decode(enable, status)[0] is accepted


def test_refusal_texts_name_the_reason():
    assert "no device" in decode(True, 2)[1]
    assert "24 V" in decode(True, 4)[1]
    assert "halt latched" in decode(True, 5)[1]
    assert decode(True, None)[1] == "no reply"
    assert "unknown" in decode(True, 9)[1]


class _Base(HasTraits):
    proxy = Any()
    realtime_mode = Bool()
    errors = List()
    #: The HV_ENABLE status byte the fake board answers.
    hv_status = Int()
    halt_reply = Any()
    snapshots = Int()
    #: Context -> the serialize flag each driver call ran with.
    serialized = Dict()
    #: Every realtime mode published, in order.
    published_realtime = List()

    def _proxy_call(self, context, call, serialize=True):
        self.serialized[context] = serialize

        if context.startswith("HV"):
            return True, SimpleNamespace(status=self.hv_status)

        if context == "halt clear":
            return True, self.halt_reply

        return True, None

    def _publish_realtime_mode(self):
        self.published_realtime.append(self.realtime_mode)

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")

    def _publish_status_snapshot(self):
        self.snapshots += 1


class _Harness(PortableDropbotStatesSettingMixinService, _Base):
    pass


def test_a_refused_hv_enable_is_published_as_an_error():
    harness = _Harness(hv_status=5)

    harness.on_set_realtime_mode_request("True")

    assert harness.errors == [
        "HV enable: REFUSED (halt latched: HALT_STATUS / HALT_CLEAR)"
    ]


@pytest.mark.parametrize("status", [2, 3, 4, 5, None])
def test_a_refused_hv_enable_takes_realtime_mode_back_off(status):
    harness = _Harness()
    harness._proxy_call = lambda context, call, serialize=True: (
        True,
        SimpleNamespace(status=status) if status is not None else None,
    )

    harness.on_set_realtime_mode_request("True")

    assert harness.realtime_mode is False
    assert harness.published_realtime == [True, False]
    assert len(harness.errors) == 1


def test_leaving_realtime_mode_skips_the_proxy_lock():
    harness = _Harness(hv_status=1, realtime_mode=True)

    harness.on_set_realtime_mode_request("False")

    assert harness.serialized == {"HV disable": False, "clear channels": False}
    assert harness.realtime_mode is False
    assert harness.published_realtime == [False]
    assert harness.errors == []


def test_an_accepted_hv_enable_raises_no_error():
    harness = _Harness(hv_status=0)

    harness.on_set_realtime_mode_request("True")

    assert harness.realtime_mode is True

    harness.hv_status = 1
    harness.on_set_realtime_mode_request("False")

    assert harness.errors == []


def test_a_refused_halt_clear_is_an_error_and_republishes_status():
    harness = _Harness(halt_reply=HaltClear(result=2, blocking=0x01, reasons=0x01))

    harness.on_clear_halt_request("")

    assert harness.errors and harness.errors[0].startswith("halt clear: REFUSED")
    assert harness.snapshots == 1


@pytest.mark.parametrize("result", [0, 1])
def test_cleared_or_nothing_latched_is_not_an_error(result):
    harness = _Harness(halt_reply=HaltClear(result=result, blocking=0, reasons=0))

    harness.on_clear_halt_request("")

    assert harness.errors == []
    assert harness.snapshots == 1
