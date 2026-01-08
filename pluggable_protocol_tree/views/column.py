from traits.api import provides, HasTraits, Instance

from ..interfaces.i_column import IColumn, IColumnModel, IColumnView, IColumnHandler
from ..models.column import (
    BaseColumnModel,
    BaseDoubleSpinBoxColumnModel,
    BaseIntSpinBoxColumnModel,
)
from .base_column_views import (
    DoubleSpinBoxColumnView,
    IntSpinBoxColumnView,
    CheckboxView,
    CheckboxHandler,
)


@provides(IColumnHandler)
class BaseColumnHandler(HasTraits):
    def on_interact(self, step, model, value):
        return model.set_value(step, value)


@provides(IColumn)
class Column(HasTraits):
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler, BaseColumnHandler())

    def traits_init(self):
        """Connect model view and the handler here"""

        self.view.model = self.model

        self.handler.model = self.model
        self.handler.view = self.view


def get_double_spinner_column(id, name, low, high, decimals):
    return Column(
        model=BaseDoubleSpinBoxColumnModel(
            col_id=id, col_name=name, low=low, high=high, decimals=decimals
        ),
        view=DoubleSpinBoxColumnView(),
    )


def get_int_spinner_column(id, name, low, high):
    return Column(
        model=BaseIntSpinBoxColumnModel(col_id=id, col_name=name, low=low, high=high),
        view=IntSpinBoxColumnView(),
    )


def get_checkbox_column(id, name):
    return Column(
        model=BaseColumnModel(col_id=id, col_name=name),
        view=CheckboxView(),
        handler=CheckboxHandler(),
    )
