from .base_column_views import (
    DoubleSpinBoxColumnView,
    IntSpinBoxColumnView,
    CheckboxView,
    CheckboxHandler,
    StringEditColumnView,
)

from .column import Column

from ...models.column import (
    BaseDoubleSpinBoxColumnModel,
    BaseIntSpinBoxColumnModel,
    BaseColumnModel,
)


def get_double_spinner_column(id, name, low, high, decimals, single_step):
    return Column(
        model=BaseDoubleSpinBoxColumnModel(
            col_id=id, col_name=name, low=low, high=high, decimals=decimals, single_step=single_step
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


def get_string_editor_column(id, name):
    return Column(
        model=BaseColumnModel(col_id=id, col_name=name),
        view=StringEditColumnView(),
    )
