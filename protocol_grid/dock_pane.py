# enthought imports
from traits.api import Str
from pyface.tasks.dock_pane import DockPane

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

        return widget

    def new_protocol(self):
        self.control.widget().new_protocol()

    def load_protocol_dialog(self):
        self.control.widget().import_from_json()

    def save_protocol_dialog(self):
        self.control.widget().save_protocol()

    def save_as_protocol_dialog(self):
        self.control.widget().save_protocol_as()

    def setup_new_experiment(self):
        self.control.widget().setup_new_experiment()