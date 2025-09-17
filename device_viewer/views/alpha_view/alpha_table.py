from traitsui.api import View, Item, ObjectColumn, TableEditor, NumericColumn, Group
from device_viewer.views.route_selection_view.route_selection_view import VisibleColumn

alpha_table_editor = TableEditor(

    columns=[
        ObjectColumn(name='key', label='Value', editable=False,),
        NumericColumn(name='alpha', label='Alpha'),
        VisibleColumn(name='visible', label='Visible', editable=False),

    ],

    show_column_labels=False,
)


alpha_table_view = View(
    Group(
        Item('alpha_map', editor=alpha_table_editor, show_label=False),
        label='Alpha Settings',
        show_border=True,
    ),
)


