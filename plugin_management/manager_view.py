"""TraitsUI layout for the Manage Plugins window: a checkbox per plugin group +
the action buttons. Pure presentation — the controller (a Handler) handles the
buttons; the model supplies ``groups``."""

from traitsui.api import Action, Item, TableEditor, View, Group
from microdrop_utils.traitsui_qt_helpers import ObjectColumn, CustomCheckboxColumn

# Buttons -> Handler methods of the same `action` name.
install_action = Action(name="Install Plugin…", action="install_plugin")
uninstall_action = Action(name="Uninstall Plugin…", action="uninstall_plugin")
apply_action = Action(name="Apply", action="apply_changes")

_groups_table = TableEditor(
    columns=[
        CustomCheckboxColumn(name="enabled", label="Enabled", editable=False),
        ObjectColumn(name="label", label="Plugin group", editable=False),
    ],
    show_lines=False,
)

manager_view = View(
    Group(
        Item("groups", show_label=False, editor=_groups_table),
    ),
    buttons=[install_action, uninstall_action, apply_action],
    title="Manage Plugins",
    resizable=True,
    kind="livemodal"
)

if __name__ == "__main__":
    from traits.api import HasTraits, List, Str, Bool, Instance, observe
    import sys
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QMainWindow
    from microdrop_style.helpers import style_app

    class Value(HasTraits):
        """A class to represent an alpha value with a key."""

        label = Str()  # The key for the alpha value
        enabled = Bool(True)  # Whether the alpha value is visible in the UI

    class Model(HasTraits):
        groups = List(Instance(Value))

        @observe("groups.items.[label, enabled]")
        def update_map(self, event):
            print(event)

    _model = Model()
    _model.groups = [
        Value(label="example_plugin_1", enabled=False),
        Value(label="example_plugin_2", enabled=True),
    ]

    app = QApplication.instance()
    style_app(app)

    widget = QWidget()
    layout = QVBoxLayout()
    widget.setLayout(layout)
    view = _model.edit_traits(view=manager_view, parent=widget)

    layout.addWidget(view.control)

    window = QMainWindow()
    window.setCentralWidget(view.control)
    window.show()

    sys.exit(app.exec())
