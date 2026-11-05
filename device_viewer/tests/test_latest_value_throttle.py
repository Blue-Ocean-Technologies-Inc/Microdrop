# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""LatestValueThrottle against a fake timer the tests fire by hand."""

# Enthought library imports.
from traits.api import Bool, Callable, Float, HasTraits, Int, Union

# Microdrop package imports.
from device_viewer.utils.latest_value_throttle import LatestValueThrottle


class FakeTimer(HasTraits):
    """The pyface single-shot timer surface the throttle uses."""

    interval = Float()
    callback = Callable()
    repeat = Union(None, Int)
    active = Bool(False)
    starts = Int(0)

    def start(self):
        self.active = True
        self.starts += 1

    def stop(self):
        self.active = False

    def fire(self):
        self.active = False
        self.callback()


def _throttle(delivered):
    return LatestValueThrottle(
        interval=0.1, callback=delivered.append, timer_factory=FakeTimer
    )


def test_a_burst_is_delivered_once_as_its_latest_value():
    delivered = []
    throttle = _throttle(delivered)

    for value in (0.1, 0.2, 0.3):
        throttle.submit(value)

    assert delivered == []
    assert throttle._timer.starts == 1
    assert throttle._timer.interval == 0.1

    throttle._timer.fire()

    assert delivered == [0.3]
    assert not throttle.pending


def test_values_after_a_delivery_start_the_timer_again():
    delivered = []
    throttle = _throttle(delivered)

    throttle.submit(0.1)
    throttle._timer.fire()
    throttle.submit(0.5)
    throttle.submit(0.6)

    assert throttle._timer.active
    assert throttle._timer.starts == 2

    throttle._timer.fire()

    assert delivered == [0.1, 0.6]


def test_cancel_drops_the_pending_value():
    delivered = []
    throttle = _throttle(delivered)

    throttle.submit(0.4)
    throttle.cancel()

    assert not throttle._timer.active

    throttle.flush()

    assert delivered == []


def test_flush_delivers_now_and_stops_the_timer():
    delivered = []
    throttle = _throttle(delivered)

    throttle.submit(0.7)
    throttle.flush()

    assert delivered == [0.7]
    assert not throttle._timer.active
