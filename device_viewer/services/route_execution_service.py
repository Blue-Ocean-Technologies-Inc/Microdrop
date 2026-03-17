from traits.api import observe, HasTraits, Instance, Bool, Any, Int, provides

from PySide6.QtCore import QTimer

from ..interfaces.i_main_model import IDeviceViewMainModel
from ..interfaces.i_route_execution_service import IRouteExecutionService
from electrode_controller.consts import electrode_state_change_publisher
from protocol_grid.services.path_execution_service import PathExecutionService

from logger.logger_service import get_logger
logger = get_logger(__name__)

@provides(IRouteExecutionService)
class RouteExecutionService(HasTraits):
    model = Instance(IDeviceViewMainModel)

    _execution_plan = Any()  # List of execution plan dicts

    _current_phase_index = Int(0)

    _user_toggled_channels = Any()  # set: channels the user manually toggled during execution
    _last_set_channels = Any()  # set: channels we programmatically set last phase (for diffing)

    _phase_timer = Any()  # QTimer instance
    _remaining_phase_time = Int(0)  # ms remaining when paused

    # ----------------------------- Timer setup -----------------------------

    def _get_or_create_timer(self):
        if self._phase_timer is None:
            self._phase_timer = QTimer()
            self._phase_timer.setSingleShot(True)
            self._phase_timer.timeout.connect(self._execute_next_phase)
        return self._phase_timer

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
            repeat_duration=0.0,
            trail_length=self.model.routes.trail_length,
            trail_overlay=self.model.routes.trail_overlay,
            paths=paths,
            activated_electrodes=activated_electrode_ids,
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
        self._remaining_phase_time = 0

        # Snapshot currently activated channels as the user's baseline selections
        self._user_toggled_channels = set(self.model.electrodes.actuated_channels)
        self._last_set_channels = set(self.model.electrodes.actuated_channels)

        # Disable route editing during execution
        for layer in self.model.routes.layers:
            layer.execution_disabled = True

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

        self._current_phase_index += 1

        duration_ms = int(plan_item["duration"] * 1000)

        # Schedule next phase
        timer = self._get_or_create_timer()
        timer.start(duration_ms)

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

    # ----------------------------- Completion / stop ------------------------

    def _on_execution_complete(self):
        logger.info("Route execution complete")
        self._cleanup(reset_phase_index=True)

    def stop_execution(self):
        """Stop a running route execution."""
        if self.model.route_execution_service_executing:
            logger.info("Stopping route execution")
            timer = self._get_or_create_timer()
            timer.stop()
            self._cleanup(reset_phase_index=True)

    def _cleanup(self, reset_phase_index=True):
        """Shared teardown for completion and stop."""
        self._capture_user_changes()

        self.model.route_execution_service_executing = False
        self.model.route_execution_service_paused = False
        self._remaining_phase_time = 0
        if reset_phase_index:
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
        timer = self._get_or_create_timer()
        self._remaining_phase_time = timer.remainingTime()
        timer.stop()
        self.model.route_execution_service_paused = True

    def resume_execution(self):
        """Resume a paused route execution."""
        if not self.model.route_execution_service_executing or not self.model.route_execution_service_paused:
            return

        logger.info("Resuming route execution")
        self.model.route_execution_service_paused = False

        if self._remaining_phase_time > 0:
            # Finish the interrupted phase
            timer = self._get_or_create_timer()
            timer.start(self._remaining_phase_time)
            self._remaining_phase_time = 0
        else:
            self._execute_next_phase()

    # ----------------------------- Phase navigation -------------------------

    def goto_prev_phase(self):
        """Navigate to the previous phase (only while paused)."""
        if not self.model.route_execution_service_paused:
            return

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
        self._current_phase_index += 1  # advance past the displayed phase
        self._remaining_phase_time = 0

    def goto_next_phase(self):
        """Navigate to the next phase (only while paused)."""
        if not self.model.route_execution_service_paused:
            return

        self._capture_user_changes()

        if self._current_phase_index >= len(self._execution_plan):
            return  # already at end

        plan_item = self._execution_plan[self._current_phase_index]
        self._apply_phase(plan_item)
        self._current_phase_index += 1
        self._remaining_phase_time = 0
