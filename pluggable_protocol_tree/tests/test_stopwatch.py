# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for ScopeStopwatch (pure, fake-clock)."""
from pluggable_protocol_tree.models.stopwatch import ScopeStopwatch


def test_not_started_reads_zero():
    sw = ScopeStopwatch()
    assert sw.elapsed(100.0) == 0.0
    assert sw.active(100.0) == 0.0


def test_elapsed_and_active_tick_together_when_running():
    sw = ScopeStopwatch()
    sw.start(0.0)
    assert sw.elapsed(2.0) == 2.0
    assert sw.active(2.0) == 2.0


def test_elapsed_ignores_pause_active_freezes():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.pause(1.0)          # active frozen at 1.0; elapsed keeps going
    assert sw.elapsed(5.0) == 5.0
    assert sw.active(5.0) == 1.0
    sw.resume(5.0)         # active resumes from 1.0
    assert sw.elapsed(6.0) == 6.0
    assert sw.active(6.0) == 2.0


def test_stop_freezes_both():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.stop(3.0)
    assert sw.elapsed(99.0) == 3.0
    assert sw.active(99.0) == 3.0


def test_resume_after_stop_is_noop():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.stop(3.0)
    sw.resume(10.0)
    assert sw.elapsed(99.0) == 3.0
    assert sw.active(99.0) == 3.0


def test_pause_before_start_is_noop():
    sw = ScopeStopwatch()
    sw.pause(5.0)
    sw.start(10.0)
    assert sw.active(12.0) == 2.0


def test_start_resets_prior_accumulation():
    sw = ScopeStopwatch()
    sw.start(0.0)
    sw.stop(5.0)
    sw.start(100.0)        # restart from zero
    assert sw.elapsed(102.0) == 2.0
    assert sw.active(102.0) == 2.0
