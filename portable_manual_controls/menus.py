from pyface.tasks.action.api import SGroup, DockPaneAction

from .consts import PKG_name, PKG


def menu_factory():
    return SGroup(
        DockPaneAction(
            id=PKG + ".help_menu",
            dock_pane_id=PKG + ".dock_pane",
            name=f"{PKG_name} &Help",
            method="show_help",
        ),
        id="portable_manual_controls_help",
    )
