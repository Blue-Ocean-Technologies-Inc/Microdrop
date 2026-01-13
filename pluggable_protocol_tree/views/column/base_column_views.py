from .column import BaseColumnHandler
from ...models.row import GroupRow
from ...interfaces.i_column import (
    IColumnView,
    IColumnModel,
    IDoubleSpinBoxColumnModel,
    INumericSpinBoxColumnModel,
    IColumnHandler,
)

from traits.api import provides, HasTraits, Instance
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QLineEdit, QSpinBox, QDoubleSpinBox


@provides(IColumnView)
class BaseColumnView(HasTraits):
    def format_display(self, value, step):
        return str(value)

    def get_check_state(self, value, step):
        return None

    def get_flags(self, step):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def create_editor(self, parent, context):
        return QLineEdit(parent)

    def set_editor_data(self, editor, value):
        editor.setText(str(value))

    def get_editor_data(self, editor):
        return editor.text()


@provides(IColumnView)
class StringEditColumnView(HasTraits):
    model = Instance(IColumnModel)

    def format_display(self, value, row):
        return str(value)

    def get_check_state(self, value, row):
        return None

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        return QLineEdit(parent)

    def set_editor_data(self, editor, value):
        editor.setText(str(value))

    def get_editor_data(self, editor):
        return editor.text()


class StringViewOnlyColumnView(StringEditColumnView):
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


@provides(IColumnView)
class CheckboxView(BaseColumnView):
    """Generic view for boolean/checkbox fields."""

    def format_display(self, value, row):
        """Return empty string for checkboxes (no text display)."""
        return ""

    def get_check_state(self, value, row):
        """Get check state, but not for groups."""

        if isinstance(row, GroupRow):
            return None
        return Qt.Checked if value else Qt.Unchecked

    def get_flags(self, row):
        """Checkboxes are checkable, but not for groups."""
        if isinstance(row, GroupRow):
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable


@provides(IColumnHandler)
class CheckboxHandler(BaseColumnHandler):
    model = Instance(IColumnModel)
    view = Instance(CheckboxView)

    def on_interact(self, row, model, value):
        # Qt sends 2 for Checked, 0 for Unchecked. Convert to Bool for Model.
        is_checked = value == Qt.Checked or value == 2 or value is True
        return model.set_value(row, is_checked)


@provides(IColumnView)
class DoubleSpinBoxColumnView(BaseColumnView):
    """Generic view for double/float fields with spin box editor."""

    model = Instance(IDoubleSpinBoxColumnModel)

    def format_display(self, value, row) -> str:
        """Format as float with 2 decimal places."""
        if value is None:
            return ""

        return f"{float(value):.2f}"

    def get_flags(self, row) -> int:
        """Editable, but not for groups."""
        if isinstance(row, GroupRow):
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        """Create a double spin box, configured from model metadata."""
        editor = QDoubleSpinBox(parent)
        editor.setMinimum(self.model.low)
        editor.setMaximum(self.model.high)
        editor.setDecimals(self.model.decimals)
        editor.setSingleStep(self.model.single_step)

        return editor

    def set_editor_data(self, editor, value) -> None:
        """Set the value in the spin box."""
        editor.setValue(float(value))

    def get_editor_data(self, editor):
        """Get the value from the spin box."""
        return editor.value()


@provides(IColumnView)
class IntSpinBoxColumnView(BaseColumnView):
    """Generic view for integer fields with spin box editor."""

    model = Instance(INumericSpinBoxColumnModel)

    def format_display(self, value, row) -> str:
        """Format as integer."""
        if value is None:
            return ""

        return str(int(value))

    def get_flags(self, step) -> int:
        """Editable, but not for groups."""
        if isinstance(step, GroupRow):
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        """Create a double spin box, configured from model metadata."""
        editor = QSpinBox(parent)
        editor.setMinimum(self.model.min_val)
        editor.setMaximum(self.model.max_val)

        return editor

    def set_editor_data(self, editor, value) -> None:
        """Set the value in the spin box."""
        editor.setValue(int(value) if value is not None else 0)

    def get_editor_data(self, editor):
        """Get the value from the spin box."""
        return editor.value()
