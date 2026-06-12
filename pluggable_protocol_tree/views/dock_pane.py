"""Pyface TaskPane hosting ProtocolTreePane.

Receives its column set from the plugin on construction and constructs
the experiment + sticky-note services from the live Envisage
application so the experiment-bar buttons drive real handlers."""

from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, List, Str

from device_viewer.consts import CHANNEL_AREAS_KEY, DEVICE_SVG_PATH_KEY
from logger.logger_service import get_logger
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.sticky_notes import StickyWindowManager
from protocol_grid.services.experiment_manager import ExperimentManager

from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext
from pluggable_protocol_tree.services.preferences import (
    ProtocolPreferences, seed_ack_times,
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
    quick_actions = List(desc="Quick actions to mount under the tree.")

    #: Protocol preferences model (the "microdrop.protocol" node). Bound to
    #: the live application's preferences in create_contents, then passed
    #: down to ProtocolTreePane, which hands it to whatever needs it (save
    #: dialogs, realtime-mode settling/restore, logging settling, column
    #: visibility).
    preferences = Instance(ProtocolPreferences)

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
        if self.preferences is None:
            self.preferences = ProtocolPreferences(preferences=app.preferences)

        # One ack-wait grid entry per wait-capable column, the plugin
        # provider's default_ack_time_s as the wait time; user-edited
        # values persisted on the node are kept.
        seed_ack_times(self.preferences, self.columns)

        experiment_manager = ExperimentManager(app.current_experiment_directory)
        sticky_manager = StickyWindowManager()

        manager = RowManager(columns=list(self.columns))
        sync = DeviceViewerSyncController(row_manager=manager)
        def _logging_device_context():
            # Decoupled: read channel areas + device SVG path from the shared
            # app_globals (published by the device viewer) rather than reaching
            # into the device-viewer pane/model.
            channel_areas, svg_path = {}, None
            try:
                # Redis JSON-stringifies the int channel keys; restore int keys
                # to match the actuation lookup (areas.get(int(ch))).
                channel_areas = {
                    int(k): float(v)
                    for k, v in (app_globals.get(CHANNEL_AREAS_KEY) or {}).items()
                }
                svg_path = app_globals.get(DEVICE_SVG_PATH_KEY)
            except Exception as e:
                logger.debug(f"logging device-context probe failed: {e}")
            return LoggingDeviceContext(
                experiment_directory=experiment_manager.get_experiment_directory(),
                device_svg_path=svg_path,
                channel_areas=channel_areas,
            )

        pane = ProtocolTreePane(
            manager,
            application=app,
            experiment_manager=experiment_manager,
            sticky_manager=sticky_manager,
            device_viewer_sync=sync,
            logging_device_context_provider=_logging_device_context,
            preferences=self.preferences,
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
