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
        # Local import to avoid pulling Qt at plugin-import time —
        # ProtocolTreePane imports PySide6 widgets eagerly.
        from pluggable_protocol_tree.views.protocol_tree_pane import (
            ProtocolTreePane,
        )

        app = self.task.window.application
        experiment_manager = ExperimentManager(app.current_experiment_directory)
        sticky_manager = StickyWindowManager()

        return ProtocolTreePane(
            list(self.columns),
            application=app,
            experiment_manager=experiment_manager,
            sticky_manager=sticky_manager,
            parent=parent,
        )
