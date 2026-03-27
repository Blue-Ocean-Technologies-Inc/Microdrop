"""Tests for repeat_duration per-loop idle phase behaviour (issue #334).

When repeat_duration > 0, each loop should independently:
  1. Calculate how many full cycles fit within that duration.
  2. Pad the remaining balance time with idle phases (holding at the start).
  3. Different-sized loops get different repetition counts and idle times.
"""

import pytest

from protocol_grid.services.path_execution_service import PathExecutionService
from protocol_grid.state.device_state import DeviceState
from protocol_grid.state.protocol_state import ProtocolStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop(n_electrodes: int) -> list:
    """Create a loop path with *n_electrodes* unique electrodes (first == last)."""
    electrodes = [f"e{i}" for i in range(n_electrodes)]
    return electrodes + [electrodes[0]]


def _make_open_path(n_electrodes: int) -> list:
    """Create an open (non-loop) path with *n_electrodes* unique electrodes."""
    return [f"e{i}" for i in range(n_electrodes)]


# ---------------------------------------------------------------------------
# calculate_effective_repetitions_for_path
# ---------------------------------------------------------------------------

class TestEffectiveRepetitions:
    """Tests for per-loop repetition calculation."""

    def test_open_path_always_returns_1(self):
        path = _make_open_path(5)
        result = PathExecutionService.calculate_effective_repetitions_for_path(
            path, original_repetitions=5, duration=1.0,
            repeat_duration=100.0, trail_length=1, trail_overlay=0,
        )
        assert result == 1

    def test_repeat_duration_zero_uses_original(self):
        """When repeat_duration <= 0, fall back to original_repetitions."""
        loop = _make_loop(5)  # 5 unique electrodes, cycle_length=5
        result = PathExecutionService.calculate_effective_repetitions_for_path(
            loop, original_repetitions=3, duration=1.0,
            repeat_duration=0.0, trail_length=1, trail_overlay=0,
        )
        assert result == 3

    def test_small_loop_fits_more_reps(self):
        """A small loop (3 electrodes) should fit more reps in 95s than a large one."""
        small_loop = _make_loop(3)  # cycle_length=3, single_cycle=3s
        large_loop = _make_loop(10)  # cycle_length=10, single_cycle=10s

        small_reps = PathExecutionService.calculate_effective_repetitions_for_path(
            small_loop, original_repetitions=1, duration=1.0,
            repeat_duration=95.0, trail_length=1, trail_overlay=0,
        )
        large_reps = PathExecutionService.calculate_effective_repetitions_for_path(
            large_loop, original_repetitions=1, duration=1.0,
            repeat_duration=95.0, trail_length=1, trail_overlay=0,
        )
        assert small_reps > large_reps

    def test_issue_example_10s_loop_95s_duration(self):
        """From the issue: a 10-electrode loop takes 10s per cycle. 95s repeat_duration
        should yield 9 full repetitions (9*10 + 1 return = 91 phases = 91s, fits in 95s).
        10 reps would be 10*10+1 = 101s which exceeds 95s."""
        loop = _make_loop(10)  # cycle_length=10
        # total_time(N) = (N * 10 + 1) * 1.0
        # N=9: 91s <= 95s  OK
        # N=10: 101s > 95s  too much
        reps = PathExecutionService.calculate_effective_repetitions_for_path(
            loop, original_repetitions=1, duration=1.0,
            repeat_duration=95.0, trail_length=1, trail_overlay=0,
        )
        assert reps == 9

    def test_original_repetitions_used_when_larger(self):
        """If user specifies more reps than duration allows, use the larger value."""
        loop = _make_loop(10)
        reps = PathExecutionService.calculate_effective_repetitions_for_path(
            loop, original_repetitions=20, duration=1.0,
            repeat_duration=95.0, trail_length=1, trail_overlay=0,
        )
        assert reps == 20


# ---------------------------------------------------------------------------
# calculate_loop_balance_idle_phases
# ---------------------------------------------------------------------------

class TestBalanceIdlePhases:
    """Tests for idle phase padding."""

    def test_no_idle_when_repeat_duration_zero(self):
        loop = _make_loop(5)
        idle = PathExecutionService.calculate_loop_balance_idle_phases(
            loop, effective_repetitions=3, duration=1.0,
            repeat_duration=0.0, trail_length=1, trail_overlay=0,
        )
        assert idle == 0

    def test_no_idle_for_open_path(self):
        path = _make_open_path(5)
        idle = PathExecutionService.calculate_loop_balance_idle_phases(
            path, effective_repetitions=1, duration=1.0,
            repeat_duration=100.0, trail_length=1, trail_overlay=0,
        )
        assert idle == 0

    def test_idle_phases_fill_balance_time(self):
        """10-electrode loop, 9 reps, 95s repeat_duration.
        Active time = (9*10+1)*1.0 = 91s. Balance = 4s. Idle phases = 4."""
        loop = _make_loop(10)
        idle = PathExecutionService.calculate_loop_balance_idle_phases(
            loop, effective_repetitions=9, duration=1.0,
            repeat_duration=95.0, trail_length=1, trail_overlay=0,
        )
        assert idle == 4

    def test_no_idle_when_time_exactly_matches(self):
        """If active time exactly equals repeat_duration, no idle needed."""
        loop = _make_loop(10)
        # 9 reps: active_time = 91s. Set repeat_duration = 91.
        idle = PathExecutionService.calculate_loop_balance_idle_phases(
            loop, effective_repetitions=9, duration=1.0,
            repeat_duration=91.0, trail_length=1, trail_overlay=0,
        )
        assert idle == 0


# ---------------------------------------------------------------------------
# calculate_step_execution_plan  -- full integration
# ---------------------------------------------------------------------------

class TestExecutionPlanWithRepeatDuration:
    """Integration tests verifying the full execution plan includes idle phases."""

    def test_single_loop_with_idle_phases(self):
        """A single loop should get idle phases appended after its active phases."""
        loop = _make_loop(10)  # cycle_length=10
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0, repetitions=1, repeat_duration=95.0,
            trail_length=1, trail_overlay=0,
            paths=[loop],
        )
        # 9 reps: active = 9*10+1 = 91 phases. idle = 4 phases. total = 95.
        assert len(plan) == 95

    def test_different_loops_get_different_reps(self):
        """Two loops of different sizes should each get their own repetition count."""
        small_loop = _make_loop(3)  # cycle_length=3
        large_loop = _make_loop(10)  # cycle_length=10

        # For repeat_duration=95:
        # small: N <= (95/1 - 1)/3 = 31.33 -> 31 reps. active = 31*3+1=94, idle=1, total=95
        # large: N <= (95/1 - 1)/10 = 9.4 -> 9 reps. active = 9*10+1=91, idle=4, total=95

        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0, repetitions=1, repeat_duration=95.0,
            trail_length=1, trail_overlay=0,
            paths=[small_loop, large_loop],
        )
        # Total phases = max(95, 95) = 95
        assert len(plan) == 95

    def test_no_idle_phases_when_repeat_duration_zero(self):
        """With repeat_duration=0, behaviour should match original (no idle phases)."""
        loop = _make_loop(5)  # cycle_length=5
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0, repetitions=2, repeat_duration=0.0,
            trail_length=1, trail_overlay=0,
            paths=[loop],
        )
        # 2 reps: active = (2-1)*5 + 5 + 1 = 11 phases
        assert len(plan) == 11

    def test_idle_phases_hold_start_electrodes(self):
        """During idle phases, the loop should hold at its starting position."""
        loop = _make_loop(4)  # e0, e1, e2, e3, e0
        # cycle_length=4.
        # effective_reps = max(1, int((10/1 - 1)/4)) = max(1, 2) = 2.
        # active phases = (2-1)*4 + 4 + 1 = 9.
        # idle = int((10 - 9) / 1) = 1. total = 10.
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0, repetitions=1, repeat_duration=10.0,
            trail_length=1, trail_overlay=0,
            paths=[loop],
        )
        assert len(plan) == 10

        # The idle phase (index 9) should hold e0 (first electrode / start position)
        assert "e0" in plan[9]["activated_electrodes"]


# ---------------------------------------------------------------------------
# calculated_duration on DeviceState
# ---------------------------------------------------------------------------

class TestDeviceStateCalculatedDuration:
    """Verify DeviceState.calculated_duration matches the execution plan."""

    def test_matches_execution_plan_length(self):
        loop = _make_loop(10)
        ds = DeviceState(paths=[loop])
        calc_time = ds.calculated_duration(
            step_duration=1.0, repetitions=1, repeat_duration=95.0,
            trail_length=1, trail_overlay=0,
        )
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0, repetitions=1, repeat_duration=95.0,
            trail_length=1, trail_overlay=0, paths=[loop],
        )
        assert calc_time == pytest.approx(len(plan) * 1.0)

    def test_at_least_repeat_duration(self):
        """calculated_duration should be >= repeat_duration."""
        loop = _make_loop(5)
        ds = DeviceState(paths=[loop])
        calc_time = ds.calculated_duration(
            step_duration=1.0, repetitions=1, repeat_duration=50.0,
            trail_length=1, trail_overlay=0,
        )
        assert calc_time >= 50.0
