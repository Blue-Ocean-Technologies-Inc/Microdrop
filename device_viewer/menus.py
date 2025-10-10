from pyface.tasks.action.api import SGroup, DockPaneAction

from .consts import PKG, PKG_name

def load_svg_dialog_menu_factory(plugin=None):
    """
    Create a menu item that makes the viewer generate the electrode view from an SVG file
    """

    return DockPaneAction(
        id=PKG + ".load_svg_file_dialog",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Load Device",
        method="load_svg_dialog"
    )

def open_svg_dialogue_menu_factory(plugin=None):
    """
    Create a menu item that makes the viewer generate an SVG file from the current electrode/channel assignment
    """

    return DockPaneAction(
        id=PKG + ".save_svg_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Save Device",
        method="save_svg_dialog"
    )