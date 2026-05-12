"""Pyface TaskPane hosting ProtocolTreePane.

Receives its column set from the plugin on construction and constructs
the experiment + sticky-note services from the live Envisage
application so the experiment-bar buttons drive real handlers."""

from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, List, Str

from microdrop_utils.sticky_notes import StickyWindowManager
from protocol_grid.services.experiment_manager import ExperimentManager

from pluggable_protocol_tree.interfaces.i_column import IColumn


class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = Str("Protocol (pluggable)")

    columns = List(Instance(IColumn))

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

        pane = ProtocolTreePane(
            manager,
            application=app,
            experiment_manager=experiment_manager,
            sticky_manager=sticky_manager,
            device_viewer_sync=sync,
            parent=parent,
        )
        pane.protocol_state_tracker.dock_pane = self
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
