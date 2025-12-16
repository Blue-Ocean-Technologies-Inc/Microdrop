from pyface.tasks.action.api import DockPaneAction, SMenu, SGroup
from pyface.action.api import Separator
from .consts import PKG

def load_svg_dialog_menu_factory():
    """
    Create a menu item that makes the viewer generate the electrode view from an SVG file
    """

    return DockPaneAction(
        id=PKG + ".load_svg_file_dialog",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Load",
        method="load_svg_dialog",
    )

def save_svg_dialogue_menu_factory():
    """
    Create a menu item that makes the viewer save current electrode/channel assignment to svg file
    """

    return DockPaneAction(
        id=PKG + ".save_svg_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Save",
        method="save_svg",
    )

def save_as_svg_dialogue_menu_factory():
    """
    Create a menu item that makes the viewer save current electrode/channel assignment to svg file
    """

    return DockPaneAction(
        id=PKG + ".save_as_svg_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Save As",
        method="save_as_svg_dialog",
    )

def generate_svg_connections_menu_factory():
    """
    Create a menu item that makes the viewer save current electrode/channel assignment to svg file
    """

    return DockPaneAction(
        id=PKG + ".generate_svg_connections",
        dock_pane_id=PKG + ".dock_pane",
        name=f"Generate Connections",
        method="generate_svg_connections",
    )

def tools_menu_factory():
    return SMenu(

        SGroup(
        load_svg_dialog_menu_factory(),
            save_svg_dialogue_menu_factory(),
            save_as_svg_dialogue_menu_factory()
        ),

    Separator(),

    generate_svg_connections_menu_factory(),

    id="device_svg_tools", name="Device"

    )