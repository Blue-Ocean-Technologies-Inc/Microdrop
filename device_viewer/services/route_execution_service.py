from traits.api import observe, HasTraits, Instance, Any, Int, Bool, provides

from ..interfaces.i_main_model import IDeviceViewMainModel
from ..interfaces.i_route_execution_service import IRouteExecutionService
from electrode_controller.consts import electrode_state_change_publisher
from protocol_grid.consts import ROUTES_EXECUTING
from protocol_grid.services.path_execution_service import PathExecutionService
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from PySide6.QtCore import QTimer
from microdrop_utils.pyside_helpers import PausableTimer

from logger.logger_service import get_logger
logger = get_logger(__name__)

@provides(IRouteExecutionService)
class RouteExecutionService(HasTraits):
    model = Instance(IDeviceViewMainModel)

    _execution_plan = Any()  # List of execution plan dicts
    _current_phase_index = Int(0)

    _user_toggled_channels = Any()  # set: channels the user manually toggled during execution
    _last_set_channels = Any()  # set: channels we programmatically set last phase (for diffing)

    _phase_timer = Any()  # PausableTimer instance
    _display_timer = Any()  # QTimer for updating status display
    _navigated_while_paused = Bool(False)

    _total_reps = Int(1)
    _total_phases = Int(0)
    _phases_per_rep = Int(1)
    _displayed_phase = Int(0)

    def __phase_timer_default(self):
        timer = PausableTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._execute_next_phase)
        return timer

    def __display_timer_default(self):
        timer = QTimer()
        timer.timeout.connect(self._update_status_display)
        return timer

    # ---------------------- User-toggle diff helper -------------------------

    def _capture_user_changes(self):
        """Diff current actuated_channels against what we last set to detect user clicks."""
        current = set(self.model.electrodes.actuated_channels)
        user_added = current - self._last_set_channels
        user_removed = self._user_toggled_channels - current
        self._user_toggled_channels = (self._user_toggled_channels | user_added) - user_removed

    # ----------------------------- Observers --------------------------------

    @observe("model:routes:execute_path_requested")
    def _execute_path_requested_change(self, event):
        """Build an execution plan for the requested routes and start phase-by-phase playback.

        One repetition is defined as every selected loop path completing one full
        cycle. The displayed rep counter is derived from the longest loop's cycle
        length so that each block of ``_phases_per_rep`` phases maps to one rep.
        Open (non-loop) paths are traversed once and do not contribute to the rep
        count.
        """
        routes_to_execute = event.new
        if not routes_to_execute:
            return

        if self.model.route_execution_service_executing:
            logger.warning("Already executing routes, ignoring new request")
            return

        if self.model.electrodes is None:
            logger.error("No electrodes model set, cannot execute routes")
            return

        # Build paths from route layers
        paths = [layer.route.route for layer in routes_to_execute]

        # Get currently activated electrode IDs (individually selected, not part of routes)
        activated_electrode_ids = []
        for channel in self.model.electrodes.actuated_channels:
            if channel in self.model.electrodes.channels_electrode_ids_map:
                activated_electrode_ids.extend(self.model.electrodes.channels_electrode_ids_map[channel])

        # Build execution plan using PathExecutionService with raw params
        plan = PathExecutionService.calculate_execution_plan_from_params(
            duration=self.model.routes.duration,
            repetitions=self.model.routes.repetitions,
            repeat_duration=self.model.routes.repeat_duration,
            trail_length=self.model.routes.trail_length,
            trail_overlay=self.model.routes.trail_overlay,
            paths=paths,
            activated_electrodes=activated_electrode_ids,
            soft_start=self.model.routes.soft_start,
            soft_terminate=self.model.routes.soft_terminate,
        )

        if not plan:
            logger.warning("Empty execution plan, nothing to execute")
            return

        logger.info(
            f"Starting route execution: {len(plan)} phases, duration={self.model.routes.duration}s"
        )

        self._execution_plan = plan
        self._current_phase_index = 0
        self.model.route_execution_service_executing = True
        self.model.route_execution_service_paused = False
        publish_message(topic=ROUTES_EXECUTING, message="true")

        # Compute phases-per-rep from the longest loop cycle across all paths
        max_cycle_length = 0
        max_effective_reps = 1
        has_loops = False
        for path in paths:
            if PathExecutionService.is_loop_path(path):
                has_loops = True
                effective_reps = PathExecutionService.calculate_effective_repetitions_for_path(
                    path,
                    self.model.routes.repetitions,
                    self.model.routes.duration,
                    self.model.routes.repeat_duration,  # repeat_duration
                    self.model.routes.trail_length,
                    self.model.routes.trail_overlay,
                )
                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(
                    path, self.model.routes.trail_length, self.model.routes.trail_overlay
                )
                cycle_length = len(cycle_phases)
                if cycle_length > max_cycle_length or (
                    cycle_length == max_cycle_length and effective_reps > max_effective_reps
                ):
                    max_cycle_length = cycle_length
                    max_effective_reps = effective_reps

        if has_loops:
            # One rep = one full cycle of the longest loop path
            self._phases_per_rep = max(max_cycle_length, 1)
            self._total_reps = max_effective_reps
        else:
            # Open paths only — no repetitions, entire plan is one rep
            self._phases_per_rep = max(len(plan), 1)
            self._total_reps = 1

        # Initialize status display
        self._total_phases = len(plan)

        # Snapshot currently activated channels as the user's baseline selections
        self._user_toggled_channels = set(self.model.electrodes.actuated_channels)
        self._last_set_channels = set(self.model.electrodes.actuated_channels)

        # Disable route editing during execution
        for layer in self.model.routes.layers:
            layer.execution_disabled = True

        self._display_timer.start(100)
        self._execute_next_phase()

    @observe("model:routes:stop_btn")
    def _on_stop_requested(self, event):
        self.stop_execution()

    @observe("model:routes:pause_btn")
    def _on_pause_requested(self, event):
        self.pause_execution()

    @observe("model:routes:resume_btn")
    def _on_resume_requested(self, event):
        self.resume_execution()

    @observe("model:routes:prev_phase_btn")
    def _on_prev_phase_requested(self, event):
        self.goto_prev_phase()

    @observe("model:routes:next_phase_btn")
    def _on_next_phase_requested(self, event):
        self.goto_next_phase()

    # ----------------------------- Execution loop ---------------------------

    def _execute_next_phase(self):
        if not self.model.route_execution_service_executing or self.model.route_execution_service_paused:
            return

        if self._current_phase_index >= len(self._execution_plan):
            self._on_execution_complete()
            return

        self._capture_user_changes()

        plan_item = self._execution_plan[self._current_phase_index]
        active_electrodes = plan_item["activated_electrodes"]

        logger.info(
            f"Phase {self._current_phase_index + 1}/{len(self._execution_plan)}: "
            f"{active_electrodes}"
        )

        self._apply_phase(plan_item)
        self._update_phase_rep_status(self._current_phase_index)

        self._current_phase_index += 1

        duration_ms = int(plan_item["duration"] * 1000)

        # Schedule next phase
        self._phase_timer.start(duration_ms)

    def _apply_phase(self, plan_item):
        """Apply a single phase: update display + hardware."""
        active_electrodes = plan_item["activated_electrodes"]

        # Map electrode IDs to channels for this phase
        id_to_channel = self.model.electrodes.electrode_ids_channels_map
        phase_channels = PathExecutionService.get_active_channels_from_map(
            id_to_channel, active_electrodes
        )

        # Merge path-phase channels with user-toggled channels
        merged_channels = phase_channels | self._user_toggled_channels

        # Update display and track what we set
        self.model.electrodes.actuated_channels = merged_channels
        self._last_set_channels = set(merged_channels)

        # Send to hardware
        electrode_state_change_publisher.publish(merged_channels)

    # ----------------------------- Status display ----------------------------

    def _update_status_display(self):
        """Called by _display_timer every 100ms to update the execution status string."""
        remaining_s = self._phase_timer.remainingTime() / 1000

        phase = self._displayed_phase
        total = self._total_phases
        current_rep = min((phase - 1) // self._phases_per_rep + 1, self._total_reps)

        self.model.execution_status = (
            f"Phase: {phase}/{total}    "
            f"Rep: {current_rep}/{self._total_reps}    "
            f"{remaining_s:.1f}s"
        )

    def _update_phase_rep_status(self, displayed_phase_index):
        """Record displayed phase (0-based) and trigger an immediate status refresh."""
        self._displayed_phase = displayed_phase_index + 1
        self._update_status_display()

    def _clear_status_display(self):
        self._display_timer.stop()
        self.model.execution_status = ""

    # ----------------------------- Completion / stop ------------------------

    def _on_execution_complete(self):
        logger.info("Route execution complete")
        self._cleanup()

    def stop_execution(self):
        """Stop a running route execution."""
        if self.model.route_execution_service_executing:
            logger.info("Stopping route execution")
            self._phase_timer.stop()
            self._cleanup()

    def _cleanup(self):
        """Shared teardown for completion and stop."""
        self._capture_user_changes()
        self._clear_status_display()

        self.model.route_execution_service_executing = False
        self.model.route_execution_service_paused = False
        publish_message(topic=ROUTES_EXECUTING, message="false")
        self._execution_plan = []
        self._current_phase_index = 0

        # Keep only user-toggled channels; clear path-driven ones
        self.model.electrodes.actuated_channels = self._user_toggled_channels
        electrode_state_change_publisher.publish(self._user_toggled_channels)

        self._last_set_channels = set()
        self._user_toggled_channels = set()

        # Re-enable route editing
        for layer in self.model.routes.layers:
            layer.execution_disabled = False

    # ----------------------------- Pause / resume ---------------------------

    def pause_execution(self):
        """Pause a running route execution."""
        if not self.model.route_execution_service_executing or self.model.route_execution_service_paused:
            return

        logger.info("Pausing route execution")
        self._phase_timer.pause()
        self.model.route_execution_service_paused = True

    def resume_execution(self):
        """Resume a paused route execution.

        If the user navigated phases while paused, replay the current phase
        from scratch. Otherwise keep the remaining timer balance.
        """
        if not self.model.route_execution_service_executing or not self.model.route_execution_service_paused:
            return

        logger.info("Resuming route execution")
        self.model.route_execution_service_paused = False

        if self._navigated_while_paused:
            # User changed phase via prev/next — replay current phase from scratch
            self._navigated_while_paused = False
            if self._current_phase_index > 0:
                self._current_phase_index -= 1
            self._phase_timer.stop()
            self._execute_next_phase()
        else:
            # Plain pause/resume — continue with remaining time
            timer = self._phase_timer
            if timer.remainingTime() > 0:
                timer.resume()
            else:
                self._execute_next_phase()

    # ----------------------------- Phase navigation -------------------------

    def goto_prev_phase(self):
        """Navigate to the previous phase (only while paused)."""
        if not self.model.route_execution_service_paused:
            return

        self._navigated_while_paused = True
        self._capture_user_changes()

        # _current_phase_index points to the NEXT phase to execute,
        # so the currently displayed phase is _current_phase_index - 1
        # Going "previous" means displaying _current_phase_index - 2
        target = self._current_phase_index - 2
        if target < 0:
            target = 0

        self._current_phase_index = target
        plan_item = self._execution_plan[self._current_phase_index]
        self._apply_phase(plan_item)
        self._update_phase_rep_status(self._current_phase_index)
        self._current_phase_index += 1  # advance past the displayed phase
        self._phase_timer.stop()  # clear any remaining time from interrupted phase

    def goto_next_phase(self):
        """Navigate to the next phase (only while paused)."""
        if not self.model.route_execution_service_paused:
            return

        self._navigated_while_paused = True
        self._capture_user_changes()

        if self._current_phase_index >= len(self._execution_plan):
            return  # already at end

        plan_item = self._execution_plan[self._current_phase_index]
        self._apply_phase(plan_item)
        self._update_phase_rep_status(self._current_phase_index)
        self._current_phase_index += 1
        self._phase_timer.stop()  # clear any remaining time from interrupted phase