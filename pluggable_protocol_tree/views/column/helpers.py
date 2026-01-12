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

from typing import Any, Type

def _create_column(
    col_id: str,
    col_name: str,
    model_cls: Type,
    view_cls: Type,
    handler: Any = None,
    **model_kwargs
):
    """
    Internal factory to consolidate Column instantiation logic.
    """
    return Column(
        model=model_cls(col_id=col_id, col_name=col_name, **model_kwargs),
        view=view_cls(),
        handler=handler,
    )

# --- Public API ---

def get_double_spinner_column(id, name, low, high, decimals=2, single_step=0.1, handler=None):
    return _create_column(
        id, name,
        BaseDoubleSpinBoxColumnModel, DoubleSpinBoxColumnView, handler,
        low=low, high=high, decimals=decimals, single_step=single_step
    )

def get_int_spinner_column(id, name, low, high, handler=None):
    return _create_column(
        id, name,
        BaseIntSpinBoxColumnModel, IntSpinBoxColumnView, handler,
        low=low, high=high
    )

def get_checkbox_column(id, name, handler=None):
    # Consolidate the specific default handler logic here
    return _create_column(
        id, name,
        BaseColumnModel, CheckboxView, handler or CheckboxHandler()
    )

def get_string_editor_column(id, name, handler=None):
    return _create_column(
        id, name,
        BaseColumnModel, StringEditColumnView, handler
    )