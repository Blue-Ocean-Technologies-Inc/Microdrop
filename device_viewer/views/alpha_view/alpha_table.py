from traitsui.api import View, Item, ObjectColumn, TableEditor, NumericColumn
from device_viewer.views.route_selection_view.route_selection_view import VisibleColumn

alpha_table_view = View(
    Item('alpha_map', show_label=False, editor=

    TableEditor(

        columns=[
            ObjectColumn(name='key', label='Value', editable=False,),
            NumericColumn(name='alpha', label='Alpha'),
            VisibleColumn(name='visible', label='Visible', editable=False),
        ],

        show_column_labels=False,
    ))
)
