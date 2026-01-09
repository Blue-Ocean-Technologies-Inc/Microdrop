from traits.api import provides, HasTraits, Str, Any, Int, Float
from ..interfaces.i_column import (
    IColumnModel,
    INumericSpinBoxColumnModel,
    IDoubleSpinBoxColumnModel,
)


@provides(IColumnModel)
class BaseColumnModel(HasTraits):
    col_id = Str
    col_name = Str
    default_value = Any(None)

    def get_value(self, row):
        return row.trait_get(self.col_id).get(self.col_id)

    def set_value(self, row, value):
        new_traits = {self.col_id: value}
        row.trait_set(**new_traits)


@provides(INumericSpinBoxColumnModel)
class BaseIntSpinBoxColumnModel(BaseColumnModel):
    low = Float(0, desc="min value in range for this column values")
    high = Float(1000, desc="max value in range for this column values")

    def traits_init(self):
        if self.default_value is None:
            self.default_value = self.low


@provides(IDoubleSpinBoxColumnModel)
class BaseDoubleSpinBoxColumnModel(BaseColumnModel):
    low = Float(0, desc="min value in range for this column values")
    high = Float(1000, desc="max value in range for this column values")
    decimals = Int(2, desc="number of decimals for this column values in spinner")
    single_step = Float(0.5, desc="single step increment value for this column values in spinner")

    def traits_init(self):
        if self.default_value is None:
            self.default_value = self.low
