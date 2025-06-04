from pyface.tasks.action.api import SGroup, DockPaneAction

from .consts import PKG, PKG_name

def device_viewer_menu_factory(plugin=None):
    """
    Create a menu for the Device Viewer
    """
    return SGroup(
        DockPaneAction(
            id=PKG + ".help_menu",
            dock_pane_id=PKG + ".pane",
            name=f"{PKG_name} Help",
            method="show_help"
        ),
        id="example_help")