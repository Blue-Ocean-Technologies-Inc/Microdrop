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
        return PGCWidget()
