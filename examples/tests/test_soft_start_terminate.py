"""Tests for soft start and soft terminate path execution (issue #317).

Verifies that PathExecutionService correctly generates ramp-up and ramp-down
phases when soft_start and soft_terminate are enabled, for both open paths
and loop paths.
"""
import pytest

from protocol_grid.services.path_execution_service import PathExecutionService


# ========================================================================
# calculate_soft_start_phases
# ========================================================================

class TestCalculateSoftStartPhases:
    def test_empty_phase(self):
        assert PathExecutionService.calculate_soft_start_phases([]) == []

    def test_single_electrode_no_ramp(self):
        """A single electrode needs no ramp-up."""
        assert PathExecutionService.calculate_soft_start_phases([0]) == []

    def test_two_electrodes(self):
        result = PathExecutionService.calculate_soft_start_phases([0, 1])
        assert result == [[0]]

    def test_three_electrodes(self):
        result = PathExecutionService.calculate_soft_start_phases([0, 1, 2])
        assert result == [[0], [0, 1]]

    def test_four_electrodes(self):
        result = PathExecutionService.calculate_soft_start_phases([5, 6, 7, 8])
        assert result == [[5], [5, 6], [5, 6, 7]]


# ========================================================================
# calculate_soft_terminate_phases
# ========================================================================

class TestCalculateSoftTerminatePhases:
    def test_empty_phase(self):
        assert PathExecutionService.calculate_soft_terminate_phases([]) == []

    def test_single_electrode_no_ramp(self):
        assert PathExecutionService.calculate_soft_terminate_phases([3]) == []

    def test_two_electrodes(self):
        result = PathExecutionService.calculate_soft_terminate_phases([3, 4])
        assert result == [[4]]

    def test_three_electrodes(self):
        result = PathExecutionService.calculate_soft_terminate_phases([3, 4, 5])
        assert result == [[4, 5], [5]]

    def test_four_electrodes(self):
        result = PathExecutionService.calculate_soft_terminate_phases([3, 4, 5, 6])
        assert result == [[4, 5, 6], [5, 6], [6]]


# ========================================================================
# calculate_trail_phases_for_path with soft start / terminate
# ========================================================================

class TestTrailPhasesWithSoftTransitions:
    """Verify that open-path trail phases include ramp-up / ramp-down."""

    def test_no_soft_flags_unchanged(self):
        """Default behaviour is unchanged when both flags are False."""
        path = ["A", "B", "C", "D", "E"]
        result_default = PathExecutionService.calculate_trail_phases_for_path(
            path, trail_length=3, trail_overlay=1
        )
        result_explicit = PathExecutionService.calculate_trail_phases_for_path(
            path, trail_length=3, trail_overlay=1, soft_start=False, soft_terminate=False
        )
        assert result_default == result_explicit

    def test_soft_start_prepends_ramp_up(self):
        path = ["A", "B", "C", "D", "E"]
        result = PathExecutionService.calculate_trail_phases_for_path(
            path, trail_length=3, trail_overlay=1, soft_start=True
        )
        # Normal phases for trail_length=3, overlay=1:
        #   [0,1,2], [2,3,4]
        # Soft start ramp from first phase [0,1,2]:
        #   [0], [0,1]
        # Full result: [0], [0,1], [0,1,2], [2,3,4]
        assert result == [[0], [0, 1], [0, 1, 2], [2, 3, 4]]

    def test_soft_terminate_appends_ramp_down(self):
        path = ["A", "B", "C", "D", "E"]
        result = PathExecutionService.calculate_trail_phases_for_path(
            path, trail_length=3, trail_overlay=1, soft_terminate=True
        )
        # Normal phases: [0,1,2], [2,3,4]
        # Soft terminate ramp from last phase [2,3,4]:
        #   [3,4], [4]
        # Full result: [0,1,2], [2,3,4], [3,4], [4]
        assert result == [[0, 1, 2], [2, 3, 4], [3, 4], [4]]

    def test_both_soft_start_and_terminate(self):
        path = ["A", "B", "C", "D", "E"]
        result = PathExecutionService.calculate_trail_phases_for_path(
            path, trail_length=3, trail_overlay=1,
            soft_start=True, soft_terminate=True
        )
        # Ramp up: [0], [0,1]
        # Normal: [0,1,2], [2,3,4]
        # Ramp down: [3,4], [4]
        assert result == [[0], [0, 1], [0, 1, 2], [2, 3, 4], [3, 4], [4]]

    def test_trail_length_1_no_ramp(self):
        """trail_length=1 means single electrode per phase; no ramp possible."""
        path = ["A", "B", "C"]
        result = PathExecutionService.calculate_trail_phases_for_path(
            path, trail_length=1, trail_overlay=0,
            soft_start=True, soft_terminate=True
        )
        # Each phase is a single electrode — ramp phases would be empty
        assert result == [[0], [1], [2]]

    def test_soft_start_short_path(self):
        """Path shorter than trail_length."""
        path = ["A", "B"]
        result = PathExecutionService.calculate_trail_phases_for_path(
            path, trail_length=3, trail_overlay=1,
            soft_start=True, soft_terminate=True
        )
        # With path shorter than trail_length, only [0,1] is produced
        # Soft start of [0,1] gives [[0]]
        # Soft terminate of [0,1] gives [[1]]
        assert result == [[0], [0, 1], [1]]


# ========================================================================
# Execution plan from params with soft transitions
# ========================================================================

class TestExecutionPlanWithSoftTransitions:
    """Integration tests for the full execution plan with soft transitions."""

    def test_open_path_soft_start_plan(self):
        """Verify execution plan phases include soft start for open paths."""
        paths = [["e0", "e1", "e2", "e3", "e4"]]
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=3,
            trail_overlay=1,
            paths=paths,
            soft_start=True,
            soft_terminate=False,
        )
        # Expected phases: [e0], [e0,e1], [e0,e1,e2], [e2,e3,e4]
        activated = [set(p["activated_electrodes"]) for p in plan]
        assert activated[0] == {"e0"}
        assert activated[1] == {"e0", "e1"}
        assert activated[2] == {"e0", "e1", "e2"}
        assert activated[3] == {"e2", "e3", "e4"}

    def test_open_path_soft_terminate_plan(self):
        """Verify execution plan phases include soft terminate for open paths."""
        paths = [["e0", "e1", "e2", "e3", "e4"]]
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=3,
            trail_overlay=1,
            paths=paths,
            soft_start=False,
            soft_terminate=True,
        )
        # Expected phases: [e0,e1,e2], [e2,e3,e4], [e3,e4], [e4]
        activated = [set(p["activated_electrodes"]) for p in plan]
        assert activated[0] == {"e0", "e1", "e2"}
        assert activated[1] == {"e2", "e3", "e4"}
        assert activated[2] == {"e3", "e4"}
        assert activated[3] == {"e4"}

    def test_open_path_both_soft_transitions_plan(self):
        """Verify execution plan with both soft start and soft terminate."""
        paths = [["e0", "e1", "e2", "e3", "e4"]]
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=0.5,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=3,
            trail_overlay=1,
            paths=paths,
            soft_start=True,
            soft_terminate=True,
        )
        activated = [set(p["activated_electrodes"]) for p in plan]
        # Ramp up: {e0}, {e0,e1}
        # Normal: {e0,e1,e2}, {e2,e3,e4}
        # Ramp down: {e3,e4}, {e4}
        assert len(plan) == 6
        assert activated[0] == {"e0"}
        assert activated[1] == {"e0", "e1"}
        assert activated[2] == {"e0", "e1", "e2"}
        assert activated[3] == {"e2", "e3", "e4"}
        assert activated[4] == {"e3", "e4"}
        assert activated[5] == {"e4"}

    def test_no_soft_flags_backward_compatible(self):
        """Without soft flags, plan is unchanged from original behavior."""
        paths = [["e0", "e1", "e2", "e3", "e4"]]
        plan_default = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=3,
            trail_overlay=1,
            paths=paths,
        )
        plan_explicit = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=3,
            trail_overlay=1,
            paths=paths,
            soft_start=False,
            soft_terminate=False,
        )
        assert len(plan_default) == len(plan_explicit)
        for a, b in zip(plan_default, plan_explicit):
            assert set(a["activated_electrodes"]) == set(b["activated_electrodes"])

    def test_loop_path_soft_start(self):
        """Verify soft start works for loop paths."""
        # Loop: e0 -> e1 -> e2 -> e3 -> e0
        paths = [["e0", "e1", "e2", "e3", "e0"]]
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=3,
            trail_overlay=1,
            paths=paths,
            soft_start=True,
            soft_terminate=False,
        )
        activated = [set(p["activated_electrodes"]) for p in plan]
        # First phases should be ramp-up (fewer electrodes than full trail_length)
        assert len(activated[0]) == 1  # soft start: 1 electrode
        assert len(activated[1]) == 2  # soft start: 2 electrodes

    def test_loop_path_soft_terminate(self):
        """Verify soft terminate works for loop paths."""
        paths = [["e0", "e1", "e2", "e3", "e0"]]
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=3,
            trail_overlay=1,
            paths=paths,
            soft_start=False,
            soft_terminate=True,
        )
        activated = [set(p["activated_electrodes"]) for p in plan]
        # Last phases should be ramp-down (fewer electrodes than full trail_length)
        assert len(activated[-1]) == 1  # soft terminate: 1 electrode
        assert len(activated[-2]) == 2  # soft terminate: 2 electrodes

    def test_execution_time_includes_soft_phases(self):
        """Verify that step execution time accounts for soft start/terminate phases."""
        from protocol_grid.state.protocol_state import ProtocolStep
        from protocol_grid.state.device_state import DeviceState

        step = ProtocolStep(parameters={
            "Duration": "1.0",
            "Repetitions": "1",
            "Repeat Duration": "0.0",
            "Trail Length": "3",
            "Trail Overlay": "1",
        })
        device_state = DeviceState(
            activated_electrodes=[],
            paths=[["e0", "e1", "e2", "e3", "e4"]],
        )

        time_without = PathExecutionService.calculate_step_execution_time(step, device_state)
        time_with_start = PathExecutionService.calculate_step_execution_time(
            step, device_state, soft_start=True
        )
        time_with_terminate = PathExecutionService.calculate_step_execution_time(
            step, device_state, soft_terminate=True
        )
        time_with_both = PathExecutionService.calculate_step_execution_time(
            step, device_state, soft_start=True, soft_terminate=True
        )

        # Base: 2 phases = 2.0s
        # Soft start adds 2 phases (trail_length=3 -> ramp [0],[0,1]) = 4.0s
        # Soft terminate adds 2 phases = 4.0s
        # Both = 6.0s
        assert time_with_start > time_without
        assert time_with_terminate > time_without
        assert time_with_both > time_with_start
        assert time_with_both > time_with_terminate
