"""TraitsUI layout for the Manage Plugins window: a Tabbed view with an
"Available Groups" tab (checkbox-per-group loader) and an "Installed Packages"
tab (a table split with a details pane, like the Browse Plugins window). Pure
presentation — the controller (a Handler) handles the buttons + per-row actions;
the model supplies ``rows`` / ``installed_rows`` / ``installed_details_text``."""
from traitsui.api import (Action, HSplit, HTMLEditor, Item, Label, TableEditor,
                          Tabbed, ToolBar, UItem, VGroup, View)

from microdrop_style.icons.icons import ICON_REFRESH
from microdrop_utils.traitsui_qt_helpers import CustomCheckboxColumn, ObjectColumn
from .installed_table import installed_table_editor

# Buttons -> Handler methods of the same `action` name.
apply_action = Action(name="Apply", action="apply_changes")
install_action = Action(name="Install Plugin…", action="install_plugin")
close_action = Action(name="Close", action="do_close")

# Refresh is a Material-glyph toolbar icon (top-left), like the Browse window;
# the controller applies the icon font to the toolbar so the label renders as a
# glyph (see ManagePluginsController._style_toolbar).
refresh_versions_action = Action(
    name=ICON_REFRESH, action="refresh_versions",
    tooltip="Refresh available versions from the plugin channel")

_INSTALLED_HELP = ("Installed plugin packages. Open docs, switch the version "
                   "(installs that build), upgrade to latest, or uninstall. "
                   "Version changes and uninstall prompt a relaunch.")

groups_table = TableEditor(
    columns=[
        CustomCheckboxColumn(name="enabled", label="Enabled", editable=False,
                             horizontal_alignment="center"),
        ObjectColumn(name="label", label="Plugin group", editable=False),
    ],
    editable=True,
    sortable=False,
    auto_size=True,   # size columns to their contents so no cell text is clipped
)

manage_plugins_view = View(
    Tabbed(
        VGroup(
            Label("Tick a group and Apply to load it now; untick to unload. "
                  "Choices persist across launches."),
            UItem("rows", editor=groups_table),
            label="Available Groups",
        ),
        HSplit(
            Item("installed_rows", show_label=False, editor=installed_table_editor,
                 tooltip=_INSTALLED_HELP),
            Item("installed_details_text", show_label=False, style="custom",
                 editor=HTMLEditor(open_externally=True)),
            label="Installed Packages",
        ),
    ),
    toolbar=ToolBar(refresh_versions_action, show_tool_names=True),
    title="Manage Plugins",
    width=680,
    height=380,
    resizable=True,
    buttons=[apply_action, install_action, close_action],
    kind="livemodal",
)
