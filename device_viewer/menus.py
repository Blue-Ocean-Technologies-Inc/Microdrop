from pyface.tasks.action.api import DockPaneAction, SMenu

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
        method="save_svg_dialog",
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


def tools_menu_factory():
    return SMenu(load_svg_dialog_menu_factory(), save_svg_dialogue_menu_factory(), save_as_svg_dialogue_menu_factory(),
                 id="device_svg_tools", name="Device")