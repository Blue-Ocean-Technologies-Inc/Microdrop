"""TraitsUI layout for the Browse Plugins window: a table of channel packages
(name/version) + a read-only details panel that fills automatically for the
selected row + action buttons. Pure presentation — the controller (a Handler)
handles the buttons; the model supplies ``packages``.
"""
from traitsui.api import Action, Item, TableEditor, View, HSplit, HTMLEditor, ToolBar

from microdrop_style.icons.icons import ICON_REFRESH
from microdrop_utils.traitsui_qt_helpers import ObjectColumn

# The Refresh action's label is the Material Symbols refresh glyph; the handler
# renders it by applying the icon font to the toolbar (see BrowsePluginsHandler).
refresh_action = Action(name=ICON_REFRESH, action="refresh",
                        tooltip="Refresh the plugin list from the channel")
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
    toolbar=ToolBar(refresh_action, show_tool_names=True),
    buttons=[install_action, close_action],
    title="Browse Plugins",
    kind="livemodal",
)
