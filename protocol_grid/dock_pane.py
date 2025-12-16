# enthought imports
from pathlib import Path

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
        widget = None
        try: 
            if hasattr(self, 'task') and self.task and hasattr(self.task, 'window'):
                widget = PGCWidget(dock_pane=self)
                app = self.task.window.application
                if app and hasattr(app, 'plugin_manager'):
                    for plugin in app.plugin_manager._plugins:
                        if hasattr(plugin, 'id') and plugin.id == "protocol_grid.plugin":
                            # set plugin reference
                            widget._protocol_grid_plugin = plugin

                            # initialize services that depend on plugin
                            widget._setup_listener()
                            
                            logger.info("protocol grid plugin references and services intialized via dock pane")
                            break
                    else:
                        logger.info("could not find protocol grid plugin")
                else:
                    logger.info("no plugin manager found in application")
            else:
                logger.info("no task/window available for plugin access")

        except Exception as e:
            logger.info(f"could not set plugin reference via dock pane: {e}")

        if widget:
            return widget
        else:
            raise