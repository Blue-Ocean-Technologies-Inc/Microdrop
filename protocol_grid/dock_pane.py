# enthought imports

from traits.api import Str
from pyface.tasks.dock_pane import DockPane

from microdrop_utils.sticky_notes import NoteLauncher
# local imports
from .widget import PGCWidget

from logger.logger_service import get_logger

from .consts import PKG, PKG_name

logger = get_logger(__name__)


class PGCDockPane(DockPane):
    """
    A dock pane to set the voltage and frequency of the dropbot device.
    """
    #### 'ITaskPane' interface ################################################

    id = f"{PKG}.dock_pane"
    name = Str(PKG_name)

    def create_contents(self, parent):
        widget = PGCWidget(dock_pane=self)
        app = self.task.window.application

        try:
            for plugin in app.plugin_manager._plugins:
                if plugin.id == "protocol_grid.plugin":
                    # set plugin reference
                    widget._protocol_grid_plugin = plugin

                    # initialize services that depend on plugin
                    widget._setup_listener()

                    logger.info("protocol grid plugin references and services intialized via dock pane")
                    break
            else:
                logger.info("could not find protocol grid plugin")

        except Exception as e:
            logger.error(f"could not set plugin reference via dock pane: {e}")
            raise Exception(f"could not set plugin reference via dock pane: {e}")

        # secondary notes widget that pgc widget could open
        self.note_launcher = NoteLauncher()
        self.note_launcher.start_daemon()

        return widget

    def load_protocol_dialog(self):
        self.control.widget().import_from_json()

    def save_as_protocol_dialog(self):
        self.control.widget().export_to_json()

    def setup_new_experiment(self):
        self.control.widget().setup_new_experiment()

    def create_new_note(self):
        widget = self.control.widget()

        base_dir = widget.experiment_manager.get_experiment_directory()
        experiment_name = base_dir.stem

        self.note_launcher.request_new_note(base_dir, experiment_name)

    def destroy(self, *args, **kwargs):
        self.note_launcher.shutdown()
        super().destroy(*args, **kwargs)