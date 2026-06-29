"""TraitsUI layout for the Manage Plugins window: a checkbox per plugin group +
the action buttons. Pure presentation — the controller (a Handler) handles the
buttons; the model supplies ``groups``."""
from traitsui.api import Action, Item, TableEditor, View
from traitsui.extras.checkbox_column import CheckboxColumn
from traitsui.table_column import ObjectColumn

# Buttons -> Handler methods of the same `action` name.
install_action = Action(name="Install Plugin…", action="install_plugin")
uninstall_action = Action(name="Uninstall Plugin…", action="uninstall_plugin")
apply_action = Action(name="Apply", action="apply_changes")
close_action = Action(name="Close", action="do_close")

_groups_table = TableEditor(
    columns=[
        CheckboxColumn(name="enabled", label="Enabled"),
        ObjectColumn(name="label", label="Plugin group", editable=False),
    ],
    sortable=False,
    configurable=False,
    deletable=False,
    show_toolbar=False,
    editable=True,
)

manager_view = View(
    Item("groups", show_label=False, editor=_groups_table),
    buttons=[install_action, uninstall_action, apply_action, close_action],
    title="Manage Plugins",
    kind="livemodal",
    resizable=True,
    width=460,
    height=320,
)
