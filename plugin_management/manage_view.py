"""TraitsUI layout for the Manage Plugins window: a Tabbed view with an
"Available Groups" tab (checkbox-per-group loader) and an "Installed Packages"
tab (a table split with a details pane, like the Browse Plugins window). Pure
presentation — the controller (a Handler) handles the buttons + per-row actions;
the model supplies ``rows`` / ``installed_rows`` / ``installed_details_text``."""
from traitsui.api import (Action, ButtonEditor, Group, HGroup, HSplit, HTMLEditor,
                          Item, Label, TableEditor, Tabbed, ToolBar, UItem, VGroup,
                          View)

from microdrop_style.button_styles import NARROW_BUTTON_STYLE
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
                   "Changes apply immediately when they can; otherwise you "
                   "are offered a relaunch, with the reason.")

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
            # Left: the table + a full-height chevron button that collapses the
            # details pane. The controller owns the toggle state + gap-tightening
            # (ManagePluginsController). Details collapsed by default.
            HGroup(
                Item("installed_rows", show_label=False,
                     editor=installed_table_editor, tooltip=_INSTALLED_HELP),
                VGroup(UItem("handler.toggle_details", style="custom", springy=True,
                             editor=ButtonEditor(label_value="handler.details_btn_label"),
                             style_sheet=NARROW_BUTTON_STYLE, tooltip="Show/Hide Details")),
            ),
            Group(
                Item("installed_details_text", show_label=False, style="custom",
                     editor=HTMLEditor(open_externally=True)),
                visible_when="handler.details_shown",
            ),
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
