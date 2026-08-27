# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import observe, Interface, Instance, Bool, Any, Int

from logger.logger_service import get_logger
logger = get_logger(__name__)

class IRouteExecutionService(Interface):
    model = Instance('device_viewer.interfaces.i_main_model.IDeviceViewMainModel')

    # Execution state
    _is_executing = Bool(False)
    _is_paused = Bool(False)
    _execution_plan = Any()  # List of execution plan dicts
    _current_phase_index = Int(0)

    @observe("model:routes:execute_path_requested")
    def _execute_path_requested_change(self, event):
        """Implement path execution routine."""

    def _execute_next_phase(self):
        """Implement method to move to next phase in a route execution routine."""

    def _on_execution_complete(self):
        """Implement post route execution routine."""

    def stop_execution(self):
        """Stop a running route execution."""

    def pause_execution(self):
        """Pause a running route execution."""

    def resume_execution(self):
        """Resume a paused route execution."""

    def goto_prev_phase(self):
        """Navigate to the previous phase (paused playback or idle nav)."""

    def goto_next_phase(self):
        """Navigate to the next phase (paused playback or idle nav)."""

    def goto_phase(self, index):
        """Jump to absolute 0-based phase ``index`` (paused or idle nav)."""

    def rebuild_phase_navigation(self):
        """(Re)build the idle phase-navigation plan (#493)."""
