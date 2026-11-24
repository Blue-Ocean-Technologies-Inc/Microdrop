# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The GUI work pacer runs one unit per turn with a pause after each, shares
one queue between chains, survives a failing unit, and schedules nothing
while idle."""

# Microdrop utils imports.
from microdrop_utils.gui_pacing import GuiWorkPacer


class FakeTimer:
    """``invoke_after`` as a list of pending (delay, callable) the test fires;
    a fake clock advances by each fired delay."""

    def __init__(self):
        self.pending = []
        self.now = 0.0

    def invoke_after(self, millisecs, callable):
        self.pending.append((millisecs, callable))

    def clock(self):
        return self.now

    def fire(self):
        millisecs, callable = self.pending.pop(0)
        self.now += millisecs / 1000
        callable()

        return millisecs


def _pacer(timer):
    return GuiWorkPacer(pause_ms=30, invoke_after=timer.invoke_after, clock=timer.clock)


def test_one_unit_per_turn_with_a_pause_after_each():
    timer = FakeTimer()
    pacer = _pacer(timer)
    ran = []

    pacer.submit(ran.append, "a")
    pacer.submit(ran.append, "b")

    # Long idle before: the first unit need not wait.
    assert [delay for delay, _ in timer.pending] == [0]

    timer.fire()

    assert ran == ["a"]
    assert [delay for delay, _ in timer.pending] == [30]

    timer.fire()

    assert ran == ["a", "b"]
    assert timer.pending == []


def test_chains_interleave_on_the_shared_queue():
    timer = FakeTimer()
    pacer = _pacer(timer)
    ran = []

    def chain(name, steps):
        ran.append(name)

        if steps > 1:
            pacer.submit(chain, name, steps - 1)

    pacer.submit(chain, "loader", 2)
    pacer.submit(chain, "sidebar", 2)

    while timer.pending:
        timer.fire()

    assert ran == ["loader", "sidebar", "loader", "sidebar"]


def test_a_unit_submitted_right_after_a_turn_still_waits_out_the_pause():
    timer = FakeTimer()
    pacer = _pacer(timer)

    pacer.submit(lambda: None)
    timer.fire()
    timer.now += 0.010
    pacer.submit(lambda: None)

    assert [delay for delay, _ in timer.pending] == [20]


def test_a_failing_unit_does_not_stop_the_queue():
    timer = FakeTimer()
    pacer = _pacer(timer)
    ran = []

    pacer.submit(lambda: 1 / 0)
    pacer.submit(ran.append, "after")

    while timer.pending:
        timer.fire()

    assert ran == ["after"]
