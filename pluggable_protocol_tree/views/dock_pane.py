"""Pyface TaskPane hosting ProtocolTreePane.

Receives its column set from the plugin on construction and constructs
the experiment + sticky-note services from the live Envisage
application so the experiment-bar buttons drive real handlers."""
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
from pluggable_protocol_tree.consts import REPEAT_DURATION_RECALC_TRIGGERS, ACK_WAIT_FOREVER
from pluggable_protocol_tree.services.phase_math import effective_repetitions_for_duration, estimate_repeat_duration_s
from pluggable_protocol_tree.services.protocol_state_tracker import PluggableProtocolStateTracker
from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, List, Str, observe

from logger.logger_service import get_logger
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.sticky_notes import StickyWindowManager
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import DeviceViewerSyncController
from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane, REPEAT_DURATION_TOLERANCE_S, \
    REPEAT_DURATION_DECIMALS
from protocol_grid.services.experiment_manager import ExperimentManager

from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.services.preferences import (
    ProtocolPreferences
)

logger = get_logger(__name__)

# Shared Redis-backed state the device viewer publishes to (channel areas, the
# device SVG path). Read here so the logging context never reaches into the
# device-viewer pane/model.
app_globals = get_microdrop_redis_globals_manager()


class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = Str("Protocol (pluggable)")

    columns = List(Instance(IColumn))
    manager = Instance(RowManager)
    sync = Instance(DeviceViewerSyncController)
    sticky_manager = Instance(StickyWindowManager)
    experiment_manager = Instance(ExperimentManager)
    quick_actions = List(desc="Quick actions to mount under the tree.")
    protocol_state_tracker = Instance(PluggableProtocolStateTracker)

    #: Protocol preferences model (the "microdrop.protocol" node). Bound to
    #: the live application's preferences in create_contents, then passed
    #: down to ProtocolTreePane, which hands it to whatever needs it (save
    #: dialogs, realtime-mode settling/restore, logging settling, column
    #: visibility).
    preferences = Instance(ProtocolPreferences)

    def _experiment_manager_default(self):
        return ExperimentManager(self.task.window.application.current_experiment_directory)

    def _sticky_manager_default(self):
        return StickyWindowManager()

    def _protocol_state_tracker_default(self):
        # dock_pane=self binds the tracker's display name ("<name> -
        # <protocol> [modified]") to this pane's title.
        return PluggableProtocolStateTracker(dock_pane=self)

    def _preferences_default(self):
        return ProtocolPreferences(preferences=self.task.window.application.preferences)

    def _sync_default(self):
        return DeviceViewerSyncController(row_manager=self.manager)

    def _manager_default(self):
        return RowManager(columns=list(self.columns))

    def traits_init(self):
        # One ack-wait grid entry per wait-capable column, the plugin
        # provider's default_ack_time_s as the wait time; user-edited
        # values persisted on the node are kept.
        self.preferences.seed_ack_times_from_columns(self.columns)
        # Handlers boot with their provider default and the observer
        # below only sees edits made from here on — push the persisted
        # grid values in once so a user-tuned wait survives a relaunch.
        self._sync_handler_ack_times()

    def create_contents(self, parent):
        pane = ProtocolTreePane(
            self.manager,
            application=self.task.window.application,
            experiment_manager=self.experiment_manager,
            sticky_manager=self.sticky_manager,
            device_viewer_sync=self.sync,
            preferences=self.preferences,
            quick_actions=list(self.quick_actions),
            protocol_state_tracker=self.protocol_state_tracker,
            parent=parent,
        )

        # Legacy protocol_grid parity: the full app opens with one default
        # step when no protocol is loaded (no-op once a protocol is loaded).
        pane._seed_default_step_if_empty()
        return pane

    # --- &Protocol menu action delegates ----------------------------

    def _pane(self):
        return self.control.widget()

    def new_protocol(self):
        self._pane().new_protocol()

    def load_protocol_dialog(self):
        self._pane().load_protocol_dialog()

    def save_protocol_dialog(self):
        self._pane().save_protocol_dialog()

    def save_as_protocol_dialog(self):
        self._pane().save_as_protocol_dialog()

    def setup_new_experiment(self):
        # Reuses the same handler the experiment-bar button drives so
        # the menu and the toolbutton stay consistent.
        self._pane()._on_new_experiment()


    ### Trait observers ###########################
    @observe("preferences.protocol_tree_ack_times.items", post_init=True)
    def _sync_handler_ack_times(self, event=None):
        """Push the Protocol Settings ack-wait grid into the column
        handlers — the only bridge from the preference to the running
        columns (handlers read their own ``ack_time_s`` at wait time).
        Idempotent: equal values are skipped, so re-running on every
        grid event is free; the event payload is never inspected (both
        patterns are observed because grid edits and node syncs REASSIGN
        the dict while other writers may mutate items). A compound's
        field cells share one handler, so its push lands exactly once.
        post_init: an immediate observer would materialize
        _preferences_default mid-construction (to compute event.old)
        before ``task`` exists; traits_init covers the initial sync."""
        ack_times = self.preferences.protocol_tree_ack_times
        for col in self.columns:
            if col.id not in ack_times:
                continue
            seconds = ack_times[col.id]
            ack_time_s = (float("inf") if seconds == ACK_WAIT_FOREVER
                          else float(seconds))
            if col.handler.ack_time_s != ack_time_s:
                logger.info(f"Protocol Tree: ack wait changed for {col.id} column: "
                            f"{col.handler.ack_time_s}s --> {ack_time_s}s")
                col.handler.ack_time_s = ack_time_s

    @observe("manager.rows_changed")
    def _on_manager_rows_changed(self, event):
        """Structural mutation — re-check the baseline path set."""
        self.protocol_state_tracker.on_structure_changed(self.manager)

    @observe("manager.cell_changed")
    def _on_manager_cell_changed(self, event):
        """Cell value edit — incremental dirty update for the one cell."""
        payload = event.new

        if not isinstance(payload, dict):
            return

        path = payload.get("path")
        col_id = payload.get("col_id")

        if path is None or col_id is None:
            return

        self.protocol_state_tracker.on_cell_changed(
            path, col_id, self.manager,
        )

        self._clamp_trail_overlay_for_row(path, col_id)
        self._reconcile_repeat_duration_for_row(path, col_id)

    @observe("task.window.application.experiment_changed")
    def _on_experiment_changed(self, event):
        # control is None until create_contents has run (the application
        # can switch experiments before this pane is mounted).
        if self.control is None:
            return
        self.control.widget()._on_experiment_changed()

    @observe("task.window.application.application_exiting")
    def _on_application_exiting(self, event):
        """Veto application exit when the protocol is dirty and the user
        elects to keep it open.

        ``event`` is a Pyface Vetoable event — setting ``event.veto = True``
        cancels the exit.
        """
        if not self.protocol_state_tracker.is_modified:
            return
        user_choice = confirm(
            self,
            "Current protocol has unsaved changes.\n"
            "Exit without saving?",
            title="Unsaved Protocol Changes",
            cancel=False,
        )
        if user_choice != YES:
            event.veto = True

    ######### Helpers ###################
    def _clamp_trail_overlay_for_row(self, path, col_id):
        """Mirror the DV sidebar's dynamic bound (trail_overlay can never
        reach trail_length): shrinking Trail Len drags an out-of-range
        Trail Overlay down with it. Runs before the repeat-duration
        reconciliation so the recalc sees the clamped overlay."""
        if col_id != "trail_length":
            return
        try:
            row = self.manager.get_row(tuple(path))
        except (IndexError, AttributeError):
            return
        max_overlay = max(0, int(getattr(row, "trail_length", 1) or 1) - 1)
        if int(getattr(row, "trail_overlay", 0) or 0) > max_overlay:
            row.trail_overlay = max_overlay
            self.manager.cell_changed = {
                "path": tuple(path), "col_id": "trail_overlay",
            }

    def _reconcile_repeat_duration_for_row(self, path, col_id):
        """Mirror the legacy auto-recalc / effective-reps coupling:

          * In Route-Reps-controlled mode (``repeat_duration_controls``
            False): edits to any geometry/timing knob refresh the
            Route Reps Dur cell with the new estimate.
          * In Route-Reps-Dur-controlled mode (flag True): edits to
            Route Reps Dur refresh the Route Reps cell with the effective
            number of full cycles that fit.

        Programmatic writes here go via ``setattr`` directly (NOT
        ``model.set_value`` and NOT through ``on_interact``) so the
        mode-switch dialog only ever fires for genuine user clicks,
        never for these reconciliation passes.
        """
        if self.control is None or self.control.widget()._is_protocol_active():
            return
        try:
            row = self.manager.get_row(tuple(path))
        except (IndexError, AttributeError):
            return
        routes = list(getattr(row, "routes", []) or [])
        if not routes:
            return
        controls = bool(getattr(row, "repeat_duration_controls", False))
        duration_s = float(getattr(row, "duration_s", 1.0) or 0.0)
        trail_length = int(getattr(row, "trail_length", 1) or 1)
        trail_overlay = int(getattr(row, "trail_overlay", 0) or 0)
        linear_repeats = bool(getattr(row, "linear_repeats", False))
        soft_start = bool(getattr(row, "soft_start", False))
        soft_end = bool(getattr(row, "soft_end", False))

        if not controls and col_id in REPEAT_DURATION_RECALC_TRIGGERS:
            n_repeats = int(getattr(row, "route_repetitions", 1) or 1)
            estimated = estimate_repeat_duration_s(
                routes=routes,
                trail_length=trail_length, trail_overlay=trail_overlay,
                n_repeats=n_repeats, step_duration_s=duration_s,
                linear_repeats=linear_repeats,
                soft_start=soft_start, soft_end=soft_end,
            )
            estimated = round(estimated, REPEAT_DURATION_DECIMALS)
            if (abs(float(getattr(row, "repeat_duration", 0.0)) - estimated)
                    >= REPEAT_DURATION_TOLERANCE_S):
                row.repeat_duration = estimated
                # Re-entrancy is bounded: see the
                # REPEAT_DURATION_RECALC_TRIGGERS guard + mode-check above;
                # "repeat_duration" is not a trigger in
                # route-reps-controlled mode so the next pass exits cleanly.
                self.manager.cell_changed = {
                    "path": tuple(path), "col_id": "repeat_duration",
                }
        elif controls and col_id == "repeat_duration":
            effective = effective_repetitions_for_duration(
                routes=routes,
                trail_length=trail_length, trail_overlay=trail_overlay,
                step_duration_s=duration_s,
                repeat_duration_s=float(getattr(row, "repeat_duration", 0.0) or 0.0),
            )
            if int(getattr(row, "route_repetitions", 1) or 1) != int(effective):
                row.route_repetitions = int(effective)
                self.manager.cell_changed = {
                    "path": tuple(path), "col_id": "route_repetitions",
                }
