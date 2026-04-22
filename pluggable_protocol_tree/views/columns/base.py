"""Base column view — non-editable text cell.

Plugin authors subclass this and override the subset of methods they
need. Concrete subclasses in this package: StringEditColumnView,
IntSpinBoxColumnView, DoubleSpinBoxColumnView, CheckboxColumnView,
ReadOnlyLabelColumnView.
"""

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QLineEdit
from traits.api import HasTraits, Bool, Instance, provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView, IColumnModel


@provides(IColumnView)
class BaseColumnView(HasTraits):
    hidden_by_default = Bool(False)
    renders_on_group = Bool(True)

    # Re-assigned by Column.traits_init; plugin authors don't set this.
    model = Instance(IColumnModel)

    def format_display(self, value, row):
        if value is None:
            return ""
        return str(value)

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def get_check_state(self, value, row):
        return None

    def create_editor(self, parent, context):
        """Default: a plain line edit. Non-editable views return None."""
        return QLineEdit(parent)

    def set_editor_data(self, editor, value):
        editor.setText("" if value is None else str(value))

    def get_editor_data(self, editor):
        return editor.text()
