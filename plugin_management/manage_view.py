"""TraitsUI layout for the Manage Plugins window: a checkbox per plugin group
+ the action buttons. Pure presentation — the controller (a Handler) handles
the buttons; the model supplies ``rows``."""
from traitsui.api import Action, Label, TableEditor, UItem, VGroup, View

from microdrop_utils.traitsui_qt_helpers import CustomCheckboxColumn, ObjectColumn

# Buttons -> Handler methods of the same `action` name.
apply_action = Action(name="Apply", action="apply_changes")
install_action = Action(name="Install Plugin…", action="install_plugin")
uninstall_action = Action(name="Uninstall Plugin…", action="uninstall_plugin")
close_action = Action(name="Close", action="do_close")

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
    VGroup(
        Label("Tick a group and Apply to load it now; untick to unload. "
              "Choices persist across launches."),
        UItem("rows", editor=groups_table),
    ),
    title="Manage Plugins",
    width=460,
    height=300,
    resizable=True,
    buttons=[apply_action, install_action, uninstall_action, close_action],
    kind="livemodal",
)
