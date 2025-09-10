from traitsui.api import View, Item, ObjectColumn, TableEditor,NumericColumn
from device_viewer.views.route_selection_view.route_selection_view import VisibleColumn


alpha_table_view = View(
    Item('alpha_map', show_label=False, editor=TableEditor(
        columns=[
            ObjectColumn(name='value', label='Value', editable=False),
            NumericColumn(name='alpha', label='Alpha', resize_mode="stretch"),
            VisibleColumn(name='visible', label='Visible', horizontal_alignment='center', width=10, editable=False),
        ]
    ))
)