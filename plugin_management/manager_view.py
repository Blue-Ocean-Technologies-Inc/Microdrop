"""TraitsUI layout for the Manage Plugins window. Pure presentation — the
Controller (manager_controller) supplies the action handlers; the model
(manager_model) supplies the state."""
from traitsui.api import (Action, HGroup, Item, Label, ListEditor, Spring,
                          UReadonly, VGroup, View)

# Action buttons -> Controller methods of the same name.
install_action = Action(name="Install Plugin…", action="install_plugin")
uninstall_action = Action(name="Uninstall…", action="uninstall_plugin",
                          enabled_when="len(handler.model.installed_rows()) > 0")
apply_action = Action(name="Apply", action="apply_changes")
close_action = Action(name="Close", action="close")


def optional_toggle_view():
    return View(HGroup(Item("on", show_label=False), UReadonly("toggle_label")))


def plugin_row_view():
    return View(HGroup(
        UReadonly("label", width=-240),
        UReadonly("version", width=-70),
        Spring(),
        Item("enabled", label="Enable"),
        # ListEditor(style="custom") renders each optional with its default view
        # (OptionalGroupToggle.traits_view, attached at the bottom of this module).
        Item("optionals", show_label=False, style="custom",
             editor=ListEditor(style="custom")),
    ))


def manager_view():
    return View(
        VGroup(
            Label("Installed plugins:"),
            # each PluginRow renders with its default view (PluginRow.traits_view).
            Item("rows", show_label=False, style="custom",
                 editor=ListEditor(style="custom")),
            show_border=True,
        ),
        buttons=[install_action, uninstall_action, apply_action, close_action],
        title="Manage Plugins",
        kind="livemodal",
        resizable=True,
        width=560,
        height=360,
    )


# Attach the per-item default views to the model classes from the VIEW module, so
# all layout lives here (the model stays view-free) while ListEditor(style="custom")
# above picks them up as each item's default view.
from plugin_management.manager_model import OptionalGroupToggle, PluginRow  # noqa: E402

PluginRow.traits_view = plugin_row_view()
OptionalGroupToggle.traits_view = optional_toggle_view()
