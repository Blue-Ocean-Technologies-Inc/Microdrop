"""TraitsUI layout for the Browse Plugins window: a table of channel packages
(name/version) + a read-only details panel that fills automatically for the
selected row + action buttons. Pure presentation — the controller (a Handler)
handles the buttons; the model supplies ``packages``.
"""
from traitsui.api import Action, Item, TableEditor, View, HSplit, HTMLEditor

from microdrop_utils.traitsui_qt_helpers import ObjectColumn

install_action = Action(name="Install", action="install_selected")
close_action = Action(name="Close", action="do_close")

_packages_table = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Name", editable=False),
        ObjectColumn(name="version", label="Version", editable=False),
    ],
    selected="selected",
    selection_mode="row",
    editable=False,
)

browse_view = View(
    HSplit(
        Item("packages", show_label=False, editor=_packages_table),
        Item("details_text", show_label=False, style="custom",
             editor=HTMLEditor(open_externally=True)),
    ),
    buttons=[install_action, close_action],
    title="Browse Plugins",
    kind="livemodal",
)
