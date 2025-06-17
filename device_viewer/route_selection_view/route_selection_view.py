from traitsui.api import View, Group, Item, BasicEditorFactory, Controller, ObjectColumn, TableEditor
from traitsui.extras.checkbox_column import CheckboxColumn
from pyface.qt.QtGui import QColor
from traitsui.toolkit_traits import Color

class ColorColumn(ObjectColumn):
    def get_cell_color(self, object):
        return QColor(object.color)

layer_table_editor = TableEditor(
    columns=[
        ColorColumn(format_func=lambda obj: '', width=1, editable=False), # Smallest possible width
        ObjectColumn(name='name', label='Layer Name', width=150, editable=False),
        CheckboxColumn(name='visible', label='Vis', width=20),
        CheckboxColumn(name='is_selected', label='Sel', width=20, editable=False)
    ],
    show_lines=False,
    selected="selected_layer",
    sortable=False

)

# Width for the whole table needs to be set in the widget itself (in the pane's create_contents)
RouteLayerView = View(
        Item('layers', editor=layer_table_editor, show_label=False), 
        resizable=True,
        title="Route Layer Selector"
)