from pyface.tasks.action.api import SGroup, DockPaneAction

from .consts import PKG, PKG_name

def open_file_dialogue_menu_factory(plugin=None):
    """
    Create a menu item that makes the viewer generate the electrode view from an SVG file
    """

    return DockPaneAction(
        id=PKG + ".open_file_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Open SVG File",
        method="open_file_dialog"
    )

def open_svg_dialogue_menu_factory(plugin=None):
    """
    Create a menu item that makes the viewer generate an SVG file from the current electrode/channel assignment
    """

    return DockPaneAction(
        id=PKG + ".open_svg_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Save to SVG",
        method="open_svg_dialog"
    )