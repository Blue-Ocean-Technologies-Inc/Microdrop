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

    # Execution state
    _is_executing = Bool(False)
    _execution_plan = Any()  # List of execution plan dicts
    _current_phase_index = Int(0)
    _user_toggled_channels = Any()  # set: channels the user manually toggled during execution
    _last_set_channels = Any()  # set: channels we programmatically set last phase (for diffing)

    @observe("model:routes:execute_path_requested")
    def _execute_path_requested_change(self, event):
        print(event)
        routes_to_execute = event.new
        if not routes_to_execute:
            return

        if self._is_executing:
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
        self._is_executing = True
        # Snapshot currently activated channels as the user's baseline selections
        self._user_toggled_channels = set(self.model.electrodes.actuated_channels)
        self._last_set_channels = set(self.model.electrodes.actuated_channels)

        # Disable route editing during execution
        for layer in self.model.routes.layers:
            layer.execution_disabled = True

        self._execute_next_phase()

    def _execute_next_phase(self):
        if not self._is_executing:
            return

        if self._current_phase_index >= len(self._execution_plan):
            self._on_execution_complete()
            return

        # Detect user channel changes since the last phase was set
        current = set(self.model.electrodes.actuated_channels)
        user_added = current - self._last_set_channels
        user_removed_from_toggled = self._user_toggled_channels - current
        self._user_toggled_channels = (self._user_toggled_channels | user_added) - user_removed_from_toggled

        plan_item = self._execution_plan[self._current_phase_index]
        active_electrodes = plan_item["activated_electrodes"]

        logger.info(
            f"Phase {self._current_phase_index + 1}/{len(self._execution_plan)}: "
            f"{active_electrodes}"
        )

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

        self._current_phase_index += 1
        duration_ms = int(plan_item["duration"] * 1000)

        # Schedule next phase
        QTimer.singleShot(duration_ms, self._execute_next_phase)


    def _on_execution_complete(self):
        logger.info("Route execution complete")

        # Capture final user changes before clearing execution state
        current = set(self.model.electrodes.actuated_channels)
        user_added = current - self._last_set_channels
        user_removed_from_toggled = self._user_toggled_channels - current
        self._user_toggled_channels = (self._user_toggled_channels | user_added) - user_removed_from_toggled

        self._is_executing = False
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

    def stop_execution(self):
        """Stop a running route execution."""
        if self._is_executing:
            logger.info("Stopping route execution")

            # Capture final user changes
            current = set(self.model.electrodes.actuated_channels)
            user_added = current - self._last_set_channels
            user_removed_from_toggled = self._user_toggled_channels - current
            self._user_toggled_channels = (self._user_toggled_channels | user_added) - user_removed_from_toggled

            self._is_executing = False
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
