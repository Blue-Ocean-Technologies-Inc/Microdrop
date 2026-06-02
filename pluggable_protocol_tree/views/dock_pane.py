"""Pyface TaskPane hosting ProtocolTreePane.

Receives its column set from the plugin on construction and constructs
the experiment + sticky-note services from the live Envisage
application so the experiment-bar buttons drive real handlers."""

from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, List, Str

from logger.logger_service import get_logger
from microdrop_utils.sticky_notes import StickyWindowManager
from protocol_grid.services.experiment_manager import ExperimentManager

from pluggable_protocol_tree.interfaces.i_column import IColumn

logger = get_logger(__name__)


class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = Str("Protocol (pluggable)")

    columns = List(Instance(IColumn))
    quick_actions = List(desc="Quick actions to mount under the tree.")

    def create_contents(self, parent):
        # Local imports to avoid pulling Qt at plugin-import time.
        from pluggable_protocol_tree.models.row_manager import RowManager
        from pluggable_protocol_tree.services.device_viewer_sync import (
            DeviceViewerSyncController,
        )
        from pluggable_protocol_tree.views.protocol_tree_pane import (
            ProtocolTreePane,
        )

        app = self.task.window.application
        experiment_manager = ExperimentManager(app.current_experiment_directory)
        sticky_manager = StickyWindowManager()

        manager = RowManager(columns=list(self.columns))
        sync = DeviceViewerSyncController(row_manager=manager)

        def _logging_device_context():
            from pluggable_protocol_tree.services.logging.models import (
                LoggingDeviceContext,
            )
            channel_areas, svg_path = {}, None
            try:
                dv_pane = self.task.window.get_dock_pane("device_viewer.dock_pane")
                model = getattr(dv_pane, "model", None)
                if model is not None:
                    channel_areas = dict(
                        model.electrodes.channel_electrode_areas_scaled_map)
                    svg_path = getattr(model.electrodes.svg_model, "filename", None)
            except Exception as e:
                logger.debug(f"logging device-context probe failed: {e}")
            return LoggingDeviceContext(
                experiment_directory=experiment_manager.get_experiment_directory(),
                device_svg_path=svg_path,
                channel_areas=channel_areas,
            )

        def _electrode_areas():
            """Per-electrode area map keyed by electrode_id (string) ->
            area in scaled mm^2 units, read from the live DV model so the
            volume-threshold column can compute target capacitance for the
            actuated electrodes of each phase.

            Returns an empty dict when the DV isn't available — the
            volume-threshold handler logs and self-disables in that case
            (same graceful-degradation posture as _logging_device_context
            above)."""
            try:
                dv_pane = self.task.window.get_dock_pane(
                    "device_viewer.dock_pane")
                model = getattr(dv_pane, "model", None)
                if model is None:
                    return {}
                svg = getattr(model.electrodes, "svg_model", None)
                if svg is None:
                    return {}
                return dict(svg.electrode_areas_scaled)
            except Exception as e:
                logger.debug(f"electrode-areas probe failed: {e}")
                return {}

        def _full_capacitance_over_area():
            """The calibrated FULL (liquid-covered) capacitance per unit
            area (pF/mm^2) from the live DV model, snapshotted at run
            start. Returns None when the DV is unavailable or the user
            hasn't calibrated — the volume-threshold handler then has no
            target reference and no-ops. Snapshotted (not taken from the
            CALIBRATION_DATA topic) because that topic only fires on
            calibration *change*, pre-run, when no step mailbox exists to
            receive it."""
            try:
                dv_pane = self.task.window.get_dock_pane(
                    "device_viewer.dock_pane")
                model = getattr(dv_pane, "model", None)
                if model is None:
                    return None
                return getattr(model, "liquid_capacitance_over_area", None)
            except Exception as e:
                logger.debug(f"full-capacitance probe failed: {e}")
                return None

        pane = ProtocolTreePane(
            manager,
            application=app,
            experiment_manager=experiment_manager,
            sticky_manager=sticky_manager,
            device_viewer_sync=sync,
            logging_device_context_provider=_logging_device_context,
            electrode_areas_provider=_electrode_areas,
            full_capacitance_provider=_full_capacitance_over_area,
            quick_actions=list(self.quick_actions),
            parent=parent,
        )
        pane.protocol_state_tracker.dock_pane = self
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
