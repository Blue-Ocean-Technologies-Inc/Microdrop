"""Phase-by-phase route execution planning for the device viewer's interactive
route preview/playback (the per-layer Run / Pause / Step controls driven by
``RouteExecutionService``).

Lifted from the legacy ``protocol_grid.services.path_execution_service`` during
PPT-9 (#371): the device viewer's route playback is a live feature that must
outlive the deleted ``protocol_grid`` plugin. Only the parameter-based planning
helpers ``RouteExecutionService`` actually uses are kept here; the legacy
``ProtocolStep`` / ``DeviceState`` couplings are replaced by tiny local stand-ins
so this module carries no ``protocol_grid`` dependency. Protocol-RUN route
execution in the new system is handled separately by ``pluggable_protocol_tree``
(``RoutesHandler`` / ``phase_math``); this module only drives the device
viewer's standalone preview.
"""

import copy
from typing import Any, Dict, List, Optional

from logger.logger_service import get_logger

logger = get_logger(__name__)


def _read_linear_repeats_from_step(step) -> bool:
    """Read the per-step ``Lin Reps`` cell value (parsed bool). Falls back to
    False if the field is missing (the params-based entry point never sets it)."""
    raw = step.parameters.get("Lin Reps", "0")
    try:
        return bool(int(raw))
    except (TypeError, ValueError):
        return str(raw).strip().lower() in ("1", "true", "yes", "on")


class _Step:
    """Minimal stand-in for the legacy ``ProtocolStep`` — just a parameters dict."""

    def __init__(self, parameters: Dict[str, str]):
        self.parameters = parameters


class _DeviceState:
    """Minimal stand-in for the legacy ``DeviceState`` — activated electrodes
    plus the list of routes (paths)."""

    def __init__(self, activated_electrodes=None, paths=None):
        self.activated_electrodes = list(activated_electrodes or [])
        self.paths = list(paths or [])

    def has_paths(self) -> bool:
        return len(self.paths) > 0


class PathExecutionService:

    @staticmethod
    def is_loop_path(path: List[str]) -> bool:
        return len(path) >= 2 and path[0] == path[-1]  # (first == last electrode)

    @staticmethod
    def calculate_effective_repetitions_for_path(path: List[str], original_repetitions: int,
                                            duration: float, repeat_duration: float,
                                            trail_length: int, trail_overlay: int) -> int:
        """Calculate how many full loop cycles fit within repeat_duration for a given path.

        When repeat_duration > 0, each loop independently calculates how many full
        cycles fit within that duration. Any remaining balance time is handled as
        idle phases in the execution plan (not here).

        When repeat_duration <= 0, the original_repetitions value is used directly.
        """
        if not PathExecutionService.is_loop_path(path):
            return 1

        cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)

        if repeat_duration <= 0:
            return original_repetitions

        cycle_length = len(cycle_phases)

        if cycle_length <= 0 or duration <= 0:
            return max(original_repetitions, 1)

        max_reps_by_duration = int(((repeat_duration / duration) - 1) / cycle_length)
        max_reps_by_duration = max(max_reps_by_duration, 1)  # at least 1 rep

        return max_reps_by_duration

    @staticmethod
    def calculate_loop_balance_idle_phases(path: List[str], effective_repetitions: int,
                                           duration: float, repeat_duration: float,
                                           trail_length: int, trail_overlay: int) -> int:
        """Calculate how many idle phases are needed after a loop finishes its cycles
        to pad out the remaining time to repeat_duration.

        Returns the number of idle phases (each lasting ``duration`` seconds) that
        should be appended after the loop's active phases to fill the balance time.
        """
        if repeat_duration <= 0 or not PathExecutionService.is_loop_path(path):
            return 0

        cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
        cycle_length = len(cycle_phases)

        if effective_repetitions > 1:
            active_phases = (effective_repetitions - 1) * cycle_length + cycle_length + 1  # +1 return phase
        else:
            active_phases = cycle_length + 1  # +1 return phase

        active_time = active_phases * duration
        balance_time = repeat_duration - active_time

        if balance_time <= 0:
            return 0

        idle_phases = int(balance_time / duration)
        return idle_phases

    @staticmethod
    def calculate_soft_start_phases(first_phase_indices: List[int]) -> List[List[int]]:
        """Generate ramp-up phases for soft start.

        Given the first full phase (e.g. [0, 1, 2] for trail_length=3),
        produces phases that incrementally add electrodes: [0], [0, 1], then the
        caller continues with the full [0, 1, 2] phase. Empty when the first
        phase has 0 or 1 electrodes (no ramp needed).
        """
        if len(first_phase_indices) <= 1:
            return []

        ramp_phases = []
        for count in range(1, len(first_phase_indices)):
            ramp_phases.append(first_phase_indices[:count])
        return ramp_phases

    @staticmethod
    def calculate_soft_terminate_phases(last_phase_indices: List[int]) -> List[List[int]]:
        """Generate ramp-down phases for soft terminate.

        Given the last full phase (e.g. [3, 4, 5] for trail_length=3), produces
        phases that incrementally remove electrodes from the front: [4, 5], [5],
        then nothing (the caller handles final deactivation). Empty when the last
        phase has 0 or 1 electrodes.
        """
        if len(last_phase_indices) <= 1:
            return []

        ramp_phases = []
        for count in range(len(last_phase_indices) - 1, 0, -1):
            # Remove from the front (leading edge stays, trailing electrodes drop off)
            ramp_phases.append(last_phase_indices[-count:])
        return ramp_phases

    @staticmethod
    def calculate_trail_phases_for_path(path: List[str], trail_length: int, trail_overlay: int,
                                        soft_start: bool = False, soft_terminate: bool = False) -> List[List[int]]:
        """calculate phase electrode indices for a path.

        Args:
            path: List of electrode IDs in the path.
            trail_length: Number of electrodes active simultaneously.
            trail_overlay: Number of electrodes that overlap between consecutive phases.
            soft_start: If True, prepend ramp-up phases (1, 2, ... trail_length electrodes).
            soft_terminate: If True, append ramp-down phases (trail_length-1, ... 2, 1 electrodes).
        """
        path_length = len(path)
        if path_length == 0:
            return []

        step_size = trail_length - trail_overlay
        if step_size <= 0:
            # not possible, fallback to current behavior
            return [[i] for i in range(path_length)]

        phases = []
        position = 0

        # cover the entire path
        while position < path_length:
            phase_electrodes = []
            for i in range(trail_length):
                electrode_index = position + i
                if electrode_index < path_length:
                    phase_electrodes.append(electrode_index)

            phases.append(phase_electrodes)

            # check if this phase includes the last electrode
            if phase_electrodes and max(phase_electrodes) == path_length - 1:
                break

            position += step_size

        # adjust the last phase if needed and if possible
        if len(phases) > 0:
            last_phase = phases[-1]

            # if the last phase has fewer than "trail_length" no.of active electrodes
            if len(last_phase) < trail_length and path_length >= trail_length:
                end_position = path_length - 1
                start_position = end_position - trail_length + 1

                start_position = max(0, start_position)

                adjusted_last_phase = list(range(start_position, end_position + 1))

                # check if adjusted last phase is identical to second-last phase
                if len(phases) > 1 and phases[-2] == adjusted_last_phase:
                    phases.pop()
                else:
                    phases[-1] = adjusted_last_phase

            # if the last phase still has fewer electrodes than trail_length after adjustment,
            # it means the path is shorter than trail_length, so remove the incomplete phase
            # and merge it with the previous phase (if it exists)
            elif len(last_phase) < trail_length:
                if len(phases) > 1:
                    phases.pop()
                # if there is only one phase and it is incomplete, keep it as is

        # Apply soft start: prepend ramp-up phases before normal execution
        if soft_start and phases:
            ramp_up = PathExecutionService.calculate_soft_start_phases(phases[0])
            phases = ramp_up + phases

        # Apply soft terminate: append ramp-down phases after normal execution
        if soft_terminate and phases:
            ramp_down = PathExecutionService.calculate_soft_terminate_phases(phases[-1])
            phases = phases + ramp_down

        return phases

    @staticmethod
    def calculate_loop_cycle_phases(path: List[str], trail_length: int, trail_overlay: int) -> List[List[int]]:
        if not PathExecutionService.is_loop_path(path):
            result = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
            logger.info(f"Open path phases: {result}")
            return result

        # for loops, make it a path without duplicating last electrode
        effective_path = path[:-1]
        effective_length = len(effective_path)

        step_size = trail_length - trail_overlay

        if step_size <= 0:
            # all positions, no smooth transition needed
            phases = [[i] for i in range(effective_length)]
            logger.info(f"Step size <= 0, generated phases: {phases}")
            return phases

        phases = []
        position = 0

        # generate phases for the loop
        while position < effective_length:
            phase_electrodes = []
            for i in range(trail_length):
                electrode_idx = (position + i) % effective_length  # wrap around
                phase_electrodes.append(electrode_idx)

            phases.append(phase_electrodes)
            position += step_size

            # check if the loop is completed
            if position >= effective_length:
                logger.info(f"Loop completed at position {position}")
                break

        logger.info(f"Final loop cycle phases: {phases}")
        return phases

    @staticmethod
    def calculate_step_execution_plan(step: "_Step", device_state: "_DeviceState",
                                      soft_start: bool = False, soft_terminate: bool = False,
                                      linear_repeats: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Build the full phase-by-phase execution plan for a step.

        Each entry describes one timed phase with its activated electrodes.
        Respects "Repeat Duration Mode" to decide whether loop repetitions are
        time-capped (with idle padding) or count-based. Soft start/terminate add
        ramp phases on top. When ``linear_repeats`` is True, linear (non-loop)
        paths are replayed ``Repetitions`` times.
        """
        duration = float(step.parameters.get("Duration", "1.0"))
        repetitions = int(step.parameters.get("Repetitions", "1"))
        repeat_duration_mode = step.parameters.get("Repeat Duration Mode", "0") == "1"
        repeat_duration = int(float(step.parameters.get("Repeat Duration", "1"))) if repeat_duration_mode else 0
        trail_length = int(step.parameters.get("Trail Length", "1"))
        trail_overlay = int(step.parameters.get("Trail Overlay", "0"))

        if linear_repeats is None:
            linear_repeats = _read_linear_repeats_from_step(step)

        step_uid = step.parameters.get("UID", "")
        step_id = step.parameters.get("ID", "")
        step_description = step.parameters.get("Description", "Step")

        execution_plan = []

        if not device_state.has_paths():
            execution_plan.append({
                "time": 0.0,
                "duration": duration,
                "activated_electrodes": copy.deepcopy(device_state.activated_electrodes),
                "step_uid": step_uid,
                "step_id": step_id,
                "step_description": step_description
            })
            return execution_plan

        # calculate effective repetitions for each path
        path_repetitions = {}
        path_info = []
        max_open_path_length = 0

        for i, path in enumerate(device_state.paths):
            is_loop = PathExecutionService.is_loop_path(path)

            if is_loop:
                effective_repetitions = PathExecutionService.calculate_effective_repetitions_for_path(
                    path, repetitions, duration, repeat_duration, trail_length, trail_overlay
                )
                path_repetitions[i] = effective_repetitions

                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)

                # Compute soft start/terminate ramp phases for this loop
                soft_start_phases = []
                soft_terminate_phases = []
                if soft_start and cycle_phases:
                    soft_start_phases = PathExecutionService.calculate_soft_start_phases(cycle_phases[0])
                if soft_terminate and cycle_phases:
                    soft_terminate_phases = PathExecutionService.calculate_soft_terminate_phases(cycle_phases[-1])

                # Active cycle phases (reps × cycle + return)
                if effective_repetitions > 1:
                    active_phases = (effective_repetitions - 1) * cycle_length + cycle_length + 1
                else:
                    active_phases = cycle_length + 1

                # Idle padding to fill remaining repeat_duration
                idle_phases = PathExecutionService.calculate_loop_balance_idle_phases(
                    path, effective_repetitions, duration, repeat_duration, trail_length, trail_overlay
                )

                loop_total_phases = (
                    len(soft_start_phases)
                    + active_phases
                    + idle_phases
                    + len(soft_terminate_phases)
                )
            else:  # open path
                open_reps = repetitions if linear_repeats else 1
                path_repetitions[i] = open_reps
                # For open paths, soft start/terminate phases are baked into the trail phases
                cycle_phases = PathExecutionService.calculate_trail_phases_for_path(
                    path, trail_length, trail_overlay,
                    soft_start=soft_start, soft_terminate=soft_terminate
                )
                cycle_length = len(cycle_phases)
                total_open_phases = cycle_length * open_reps
                max_open_path_length = max(max_open_path_length, total_open_phases)
                loop_total_phases = total_open_phases
                active_phases = total_open_phases
                idle_phases = 0
                soft_start_phases = []
                soft_terminate_phases = []

            path_info.append({
                "path": path,
                "is_loop": is_loop,
                "cycle_length": cycle_length,
                "cycle_phases": cycle_phases,
                "loop_total_phases": loop_total_phases,
                "active_phases": active_phases,
                "idle_phases": idle_phases,
                "effective_repetitions": path_repetitions[i],
                "soft_start_phases": soft_start_phases,
                "soft_terminate_phases": soft_terminate_phases,
            })

        # calculate total phases based on the longest duration needed
        max_loop_total_phases = 0
        for path_data in path_info:
            if path_data["is_loop"]:
                max_loop_total_phases = max(max_loop_total_phases, path_data["loop_total_phases"])

        total_phases = max(max_loop_total_phases, max_open_path_length)

        for phase_idx in range(total_phases):
            # individually activated electrodes always active
            phase_electrodes = set(copy.deepcopy(device_state.activated_electrodes))

            for path_idx, path_data in enumerate(path_info):
                path = path_data["path"]
                is_loop = path_data["is_loop"]
                cycle_length = path_data["cycle_length"]
                cycle_phases = path_data["cycle_phases"]
                active_phases = path_data["active_phases"]
                idle_phases = path_data["idle_phases"]
                path_total_phases = path_data["loop_total_phases"]
                effective_repetitions = path_data["effective_repetitions"]
                soft_start_phases = path_data["soft_start_phases"]
                soft_terminate_phases = path_data["soft_terminate_phases"]

                if is_loop:
                    num_soft_start = len(soft_start_phases)
                    num_soft_terminate = len(soft_terminate_phases)

                    # Phase layout:
                    #   [soft_start][active cycles][idle pad][soft_terminate]
                    if phase_idx >= path_total_phases:
                        continue

                    # Soft start ramp-up
                    if phase_idx < num_soft_start:
                        electrode_indices = soft_start_phases[phase_idx]
                        for electrode_idx in electrode_indices:
                            if electrode_idx < len(path) - 1:
                                electrode_id = path[electrode_idx]
                                phase_electrodes.add(electrode_id)
                        continue

                    adjusted_idx = phase_idx - num_soft_start

                    # Soft terminate ramp-down at the very end
                    if adjusted_idx >= active_phases + idle_phases:
                        terminate_idx = adjusted_idx - (active_phases + idle_phases)
                        if terminate_idx < num_soft_terminate:
                            electrode_indices = soft_terminate_phases[terminate_idx]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path) - 1:
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes.add(electrode_id)
                        continue

                    # Idle phase: hold at the loop's start position
                    if adjusted_idx >= active_phases:
                        if len(cycle_phases) > 0:
                            electrode_indices = cycle_phases[0]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path) - 1:
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes.add(electrode_id)
                        continue

                    # Normal loop cycle logic (using adjusted_idx)
                    if effective_repetitions > 1:
                        # Determine which repetition and phase within that repetition
                        if adjusted_idx < (effective_repetitions - 1) * cycle_length:
                            # Intermediate repetitions (no return phase)
                            phase_in_cycle = adjusted_idx % cycle_length
                            is_return_phase = False
                        else:
                            # Last repetition (with return phase)
                            phase_in_last_rep = adjusted_idx - (effective_repetitions - 1) * cycle_length
                            if phase_in_last_rep < cycle_length:
                                phase_in_cycle = phase_in_last_rep
                                is_return_phase = False
                            else:
                                phase_in_cycle = 0
                                is_return_phase = True
                    else:
                        if adjusted_idx < cycle_length:
                            phase_in_cycle = adjusted_idx
                            is_return_phase = False
                        else:
                            phase_in_cycle = 0
                            is_return_phase = True

                    if is_return_phase:
                        # Return phase - use first phase of the cycle
                        if 0 < len(cycle_phases):
                            electrode_indices = cycle_phases[0]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path) - 1:  # exclude duplicate
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes.add(electrode_id)
                    else:
                        # Regular phase
                        if phase_in_cycle < len(cycle_phases):
                            electrode_indices = cycle_phases[phase_in_cycle]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path) - 1:  # exclude duplicate
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes.add(electrode_id)
                else:
                    # Open path: with linear_repeats, total active phases =
                    # cycle_length * repetitions; we wrap phase_idx around the
                    # cycle so the trail replays from the start each rep.
                    if phase_idx < path_total_phases:
                        phase_in_cycle = phase_idx % cycle_length if cycle_length > 0 else 0
                        if phase_in_cycle < len(cycle_phases):
                            electrode_indices = cycle_phases[phase_in_cycle]
                            for electrode_idx in electrode_indices:
                                if electrode_idx < len(path):
                                    electrode_id = path[electrode_idx]
                                    phase_electrodes.add(electrode_id)

            execution_plan.append({
                "time": phase_idx * duration,
                "duration": duration,
                "activated_electrodes": list(phase_electrodes),
                "step_uid": step_uid,
                "step_id": step_id,
                "step_description": step_description
            })

        return execution_plan

    @staticmethod
    def calculate_execution_plan_from_params(
        duration: float,
        repetitions: int,
        repeat_duration: float,
        trail_length: int,
        trail_overlay: int,
        paths: List[List[str]],
        activated_electrodes: List[str] = None,
        step_uid: str = "",
        step_id: str = "",
        step_description: str = "Step",
        repeat_duration_mode: bool = True,
        soft_start: bool = False,
        soft_terminate: bool = False,
        linear_repeats: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Calculate an execution plan from raw parameters (no ProtocolStep /
        DeviceState needed).

        When ``repeat_duration_mode`` is True (default), ``repeat_duration`` caps
        how many loops fit in the allotted time and idle phases pad any remaining
        balance. When False, each loop runs exactly ``repetitions`` times.
        ``soft_start`` / ``soft_terminate`` prepend/append ramp phases.
        """
        step = _Step(parameters={
            "Duration": str(duration),
            "Repetitions": str(repetitions),
            "Repeat Duration": str(repeat_duration),
            "Repeat Duration Mode": "1" if repeat_duration_mode else "0",
            "Trail Length": str(trail_length),
            "Trail Overlay": str(trail_overlay),
            "UID": step_uid,
            "ID": step_id,
            "Description": step_description,
        })
        device_state = _DeviceState(
            activated_electrodes=list(activated_electrodes or []),
            paths=paths,
        )
        return PathExecutionService.calculate_step_execution_plan(
            step, device_state,
            soft_start=soft_start, soft_terminate=soft_terminate,
            linear_repeats=linear_repeats,
        )

    @staticmethod
    def get_active_channels_from_map(id_to_channel: Dict[str, int], active_electrodes: List[str]) -> set:
        """Get active channels from a direct id_to_channel mapping."""
        active_channels = set()
        for electrode_id in active_electrodes:
            if electrode_id in id_to_channel:
                channel = id_to_channel[electrode_id]
                if channel is not None:
                    active_channels.add(channel)
        return active_channels
