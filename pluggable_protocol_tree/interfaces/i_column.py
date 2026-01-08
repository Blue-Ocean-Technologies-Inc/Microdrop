from traits.api import Interface, Any, Instance, Str, Float, Int
from .i_step import IStep

from pyface.qt.QtGui import QWidget


class IColumnModel(Interface):
    col_id = Str
    col_name = Str

    def get_value(self, step: IStep) -> Any:
        """get value from given step of this field"""

    def set_value(self, step: IStep, value: Any) -> bool:
        """set value for this column in given step"""


class INumericSpinBoxColumnModel(IColumnModel):
    low = Float(desc="min value in range for this column values")
    high = Float(desc="max value in range for this column values")


class IDoubleSpinBoxColumnModel(IColumnModel):
    low = Float(desc="min value in range for this column values")
    high = Float(desc="max value in range for this column values")
    decimals = Int(desc="number of decimals for this column values in spinner")


class IColumnView(Interface):

    model = Instance(IColumnModel)

    def format_display(self, value: Any, step: IStep) -> str:
        """Text to show for this column on protocol tree if string display required"""

    def get_check_state(self, value: Any, step: IStep) -> Any:
        """return None if no checkbox display, else return check state"""

    def get_flags(self, step: IStep) -> int:
        """is it checkable, editable etc"""

    def create_editor(self, parent: QWidget, context: Any) -> QWidget:
        """Double spin box, check box, line edit, etc"""

    def set_editor_data(self, editor: QWidget, value: Any):
        """Used in QStyledItemDelegate. Define if needed."""

    def get_editor_data(self, editor: QWidget) -> Any:
        """Used in QStyledItemDelegate. Define if needed"""


class IColumnHandler(Interface):
    model = Instance(IColumnModel)
    view = Instance(IColumnView)

    def on_interact(self, step: IStep, model: IColumnModel, value: Any) -> bool:
        pass


class IColumn(Interface):
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler)

    def traits_init(self):
        """Connect model view and the handler here"""

        self.view.model = self.model
        self.handler.model = self.model
        self.handler.view = self.view
