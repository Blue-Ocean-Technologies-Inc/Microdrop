from pyface.tasks.action.api import SGroup, DockPaneAction

from .consts import PKG_name, PKG


def menu_factory():
    """
    Create a menu for the Dropbot Status And Controls dock pane.
    """
    return SGroup(
        DockPaneAction(
            id=PKG + ".help_menu",
            dock_pane_id=PKG + ".dock_pane",
            name=f"{PKG_name} &Help",
            method="show_help"
        ),
        id="example_help")
