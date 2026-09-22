# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The filter-wheel request moves through the generated motor proxy (its
reply waits up to 60 s) — never the vendor uart facade's 5 s setFilter,
which logs a wheel still turning as a failure. Hardware-free, no Redis."""

# Enthought library imports.
from traits.api import Any, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.services.portable_dropbot_motors_mixin_service import (
    PortableDropbotMotorsMixinService,
)


class _Motor:
    def __init__(self, log):
        self.log = log

    def fluorescence_ctrl(self, position):
        self.log.append(f"filter {position}")
        return object()


class _Uart:
    def setFilter(self, position):
        raise AssertionError("the uart facade must not be used for filter moves")


class _Session:
    def __init__(self, log):
        self.motor = _Motor(log)
        self.uart = _Uart()


class _Base(HasTraits):
    proxy = Any()
    log = List()
    snapshots = List()

    def _proxy_call(self, context, call):
        return True, call()

    def _publish_status_snapshot(self):
        self.snapshots.append(True)


class _Harness(PortableDropbotMotorsMixinService, _Base):
    pass


def test_set_filter_moves_through_the_motor_proxy_and_republishes_status():
    h = _Harness()
    h.proxy = _Session(h.log)

    h.on_set_filter_request("3")

    assert h.log == ["filter 3"]
    assert h.snapshots == [True]


def test_set_filter_ignores_a_position_the_wheel_does_not_have():
    h = _Harness()
    h.proxy = _Session(h.log)

    h.on_set_filter_request("7")

    assert h.log == []
    assert h.snapshots == []
