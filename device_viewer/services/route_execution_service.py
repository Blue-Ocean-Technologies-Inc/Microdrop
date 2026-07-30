import json

from traits.api import observe, HasTraits, Instance, Bool, Int, List, Set, provides

from ..interfaces.i_main_model import IDeviceViewMainModel
from ..interfaces.i_route_execution_service import IRouteExecutionService
from electrode_controller.consts import electrode_state_change_publisher
from ..consts import ROUTES_EXECUTING, PHASE_NAVIGATION_STATE
from microdrop_utils.route_execution import PathExecutionService
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from PySide6.QtCore import QTimer
from microdrop_utils.pyside_helpers import PausableTimer

from logger.logger_service import get_logger
logger = get_logger(__name__)

@provides(IRouteExecutionService)
class RouteExecutionService(HasTraits):
    model = Instance(IDeviceViewMainModel)

    #: Execution plan dicts from the centralized PathExecutionService.
    _execution_plan = List()
    _current_phase_index = Int(0)

    #: Channels the user manually toggled during execution.
    _user_toggled_channels = Set()
    #: Channels we programmatically set last phase (for diffing).
    _last_set_channels = Set()

    _phase_timer = Instance(PausableTimer)
    _display_timer = Instance(QTimer)
    _navigated_while_paused = Bool(False)

    _total_reps = Int(1)
    _total_phases = Int(0)
    _phases_per_rep = Int(1)
    _displayed_phase = Int(0)

    #: Set by the dock pane while applying an inbound step message, so the
    #: play-checkbox/param-edit rebuild observer doesn't fire mid-apply on
    #: stale (old-step) execution-plan state (#493 review F2).
    suspend_nav_rebuild = Bool(False)

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

    def _build_execution_plan(self, routes_to_execute):
        """Phase plan for the given layers from the live sidebar params.
        Shared by timed playback and idle phase navigation (#493)."""
        paths = [layer.route.route for layer in routes_to_execute]

        # Currently activated electrode IDs (individually selected, not part
        # of routes) ride along in every phase.
        activated_electrode_ids = []
        for channel in self.model.electrodes.actuated_channels:
            if channel in self.model.electrodes.channels_electrode_ids_map:
                activated_electrode_ids.extend(
                    self.model.electrodes.channels_electrode_ids_map[channel])

        return PathExecutionService.calculate_execution_plan_from_params(
            duration=self.model.routes.duration,
            repetitions=self.model.routes.repetitions,
            repeat_duration=self.model.routes.repeat_duration,
            trail_length=self.model.routes.trail_length,
            trail_overlay=self.model.routes.trail_overlay,
            paths=paths,
            activated_electrodes=activated_electrode_ids,
            soft_start=self.model.routes.soft_start,
            soft_terminate=self.model.routes.soft_terminate,
            linear_repeats=bool(self.model.routes.linear_repeats),
        )

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

        # Build paths from route layers (kept for the rep breakdown below)
        paths = [layer.route.route for layer in routes_to_execute]

        linear_repeats = bool(self.model.routes.linear_repeats)

        plan = self._build_execution_plan(routes_to_execute)

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
        publish_message(topic=ROUTES_EXECUTING, message=str(True))

        # Phases-per-rep / total reps from the centralized logic (shared
        # with the protocol tree so both report the same breakdown).
        self._phases_per_rep, self._total_reps = (
            PathExecutionService.calculate_phase_rep_breakdown(
                paths, len(plan),
                duration=self.model.routes.duration,
                repetitions=self.model.routes.repetitions,
                repeat_duration=self.model.routes.repeat_duration,
                trail_length=self.model.routes.trail_length,
                trail_overlay=self.model.routes.trail_overlay,
                soft_start=self.model.routes.soft_start,
                soft_terminate=self.model.routes.soft_terminate,
                linear_repeats=linear_repeats,
            ))

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

    # ----------------------- Idle phase navigation (#493) -------------------

    @observe("model:phase_navigation_mode")
    def _phase_navigation_mode_changed(self, event):
        if event.new:
            self.start_phase_navigation()
        else:
            self.stop_phase_navigation()

    def _nav_active(self):
        """Idle phase navigation is in charge: mode on, no timed playback,
        no protocol run (kept local rather than relying solely on the dock
        pane's force-exit observer ordering, #493 review F4)."""
        return (self.model.phase_navigation_mode
                and not self.model.route_execution_service_executing
                and not self.model.protocol_running)

    def start_phase_navigation(self):
        if self.model.route_execution_service_executing:
            self.stop_execution()
        self.rebuild_phase_navigation()

    def stop_phase_navigation(self):
        if self.model.route_execution_service_executing:
            return  # timed playback owns the display; nothing to restore
        if self._execution_plan:
            self._capture_user_changes()
            # Drop the applied phase, keep what the user toggled themselves.
            self.model.electrodes.actuated_channels = self._user_toggled_channels
            # The mode trait is already False by the time this observer runs,
            # so the dock pane's publish_electrode_update gate (which requires
            # free_mode or phase_navigation_mode while idle) is closed and
            # would silently drop this restore — publish explicitly instead,
            # same reason _cleanup does (#493 review F1).
            electrode_state_change_publisher.publish(self._user_toggled_channels)
        self._execution_plan = []
        self._current_phase_index = 0
        self._last_set_channels = set()
        self._user_toggled_channels = set()
        self.model.execution_status = ""
        self._publish_phase_nav_state()

    def rebuild_phase_navigation(self):
        """(Re)build the idle-nav plan from the play-enabled layers and show
        phase 0. Called on mode entry, on step selection change (dock pane),
        and on play-checkbox / execution-param edits. No-op unless idle
        navigation is in charge."""
        if not self._nav_active():
            return
        if self.suspend_nav_rebuild:
            return
        if self._execution_plan:
            self._capture_user_changes()
            # Restore the user baseline before re-snapshotting it, so the
            # previous plan's phase electrodes don't leak into the new plan.
            self.model.electrodes.actuated_channels = self._user_toggled_channels
        routes_to_execute = [layer for layer in self.model.routes.layers
                             if layer.selected_for_run]
        plan = (self._build_execution_plan(routes_to_execute)
                if routes_to_execute else [])
        self._user_toggled_channels = set(self.model.electrodes.actuated_channels)
        self._last_set_channels = set(self.model.electrodes.actuated_channels)
        self._execution_plan = plan
        self._current_phase_index = 0
        if plan:
            logger.info(f"Idle phase navigation: plan rebuilt, {len(plan)} phases")
            self._apply_phase(plan[0])
            self._update_phase_rep_status(0)
            self._current_phase_index = 1
        else:
            self.model.execution_status = ""
        self._publish_phase_nav_state()

    def _publish_phase_nav_state(self):
        displayed = (self._current_phase_index - 1) if self._execution_plan else 0
        publish_message(
            topic=PHASE_NAVIGATION_STATE,
            message=json.dumps({
                "phase_index": max(0, displayed),
                "phase_total": len(self._execution_plan),
            }))

    @observe("model:routes:layers:items:selected_for_run")
    @observe("model:routes:[duration, repetitions, repeat_duration, "
             "trail_length, trail_overlay, soft_start, soft_terminate, "
             "linear_repeats]")
    def _rebuild_nav_on_edit(self, event):
        self.rebuild_phase_navigation()

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

        # Keep the tree's phase position current during sidebar playback too
        # (#493 review F3): otherwise it freezes as soon as Run takes over.
        if self.model.phase_navigation_mode:
            self._publish_phase_nav_state()

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
        # electrode_state_change_publisher.publish(merged_channels)
        # actuated channels trait change should trigger the publisher in dv dock pane observer

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
        """Record displayed phase (0-based) and refresh the status string."""
        self._displayed_phase = displayed_phase_index + 1
        if self._nav_active():
            # No timer/rep readout while idle-stepping — just the position.
            self.model.execution_status = (
                f"Phase: {self._displayed_phase}/{len(self._execution_plan)}")
        else:
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
        publish_message(topic=ROUTES_EXECUTING, message=str(False))
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

        # If the user played routes while the idle nav mode was on, hand the
        # display back to phase navigation (#493).
        if self.model.phase_navigation_mode:
            self.rebuild_phase_navigation()

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
        """Navigate to the previous phase (paused playback or idle nav)."""
        # _current_phase_index points at the NEXT phase, so the displayed
        # phase is index-1 and "previous" is index-2 (goto_phase clamps).
        self.goto_phase(self._current_phase_index - 2)

    def goto_next_phase(self):
        """Navigate to the next phase (paused playback or idle nav)."""
        self.goto_phase(self._current_phase_index)

    def goto_phase(self, index):
        """Jump to absolute 0-based phase ``index`` (clamped into the plan).
        Active while playback is paused or idle navigation is in charge."""
        if not (self.model.route_execution_service_paused or self._nav_active()):
            return
        if not self._execution_plan:
            return

        if self.model.route_execution_service_paused:
            # Only paused playback replays from scratch on resume; idle-nav
            # has no timer to replay and must not set this flag (#493).
            self._navigated_while_paused = True
        self._capture_user_changes()

        target = max(0, min(int(index), len(self._execution_plan) - 1))
        self._current_phase_index = target
        plan_item = self._execution_plan[self._current_phase_index]
        self._apply_phase(plan_item)
        self._update_phase_rep_status(self._current_phase_index)
        self._current_phase_index += 1  # advance past the displayed phase
        self._phase_timer.stop()  # clear any remaining time from interrupted phase

        # Publish whenever the mode is on, regardless of whether idle nav or
        # timed playback currently owns the display, so the tree's phase
        # position tracks playback too (#493 review F3). _publish_phase_nav_state
        # computes displayed = _current_phase_index - 1, which is correct in
        # both contexts.
        if self.model.phase_navigation_mode:
            self._publish_phase_nav_state()