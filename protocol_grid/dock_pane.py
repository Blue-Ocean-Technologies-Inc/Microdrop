# enthought imports
from traits.api import Str
from pyface.tasks.dock_pane import DockPane

# local imports
from .widget import PGCWidget

from .consts import PKG, PKG_name


class PGCDockPane(DockPane):
    """
    A dock pane to set the voltage and frequency of the dropbot device.
    """
    #### 'ITaskPane' interface ################################################

    id = Str(PKG + ".widget")
    name = Str(PKG_name)

    def create_contents(self, parent):
        widget = PGCWidget()
        
        # pass plugin reference to widget if available
        try:
            if hasattr(self, 'task') and self.task and hasattr(self.task, 'window'):
                app = self.task.window.application
                if app and hasattr(app, 'plugin_manager'):
                    for plugin in app.plugin_manager._plugins:
                        if hasattr(plugin, 'id') and plugin.id == "protocol_grid.plugin":
                            widget._protocol_grid_plugin = plugin
                            break
        except Exception as e:
            return widget

        return widget
