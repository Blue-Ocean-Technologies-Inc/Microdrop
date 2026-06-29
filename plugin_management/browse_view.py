"""TraitsUI layout for the Browse Plugins window: a table of channel packages
(name/version) + a read-only details panel + action buttons. Pure presentation —
the controller (a Handler) handles the buttons; the model supplies ``packages``.
"""
from traitsui.api import Action, Item, TableEditor, View, VGroup, TextEditor

from microdrop_utils.traitsui_qt_helpers import ObjectColumn

details_action = Action(name="More details", action="show_details")
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
    sortable=False,
)

browse_view = View(
    VGroup(
        Item("packages", show_label=False, editor=_packages_table),
        Item("details_text", show_label=False, style="custom",
             editor=TextEditor(read_only=True)),
    ),
    buttons=[details_action, install_action, close_action],
    title="Browse Plugins",
    kind="livemodal",
    resizable=True,
    width=620,
    height=480,
)
