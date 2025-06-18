from traitsui.api import View, Group, Item, BasicEditorFactory, Controller, ObjectColumn, TableEditor
from traitsui.extras.checkbox_column import CheckboxColumn
from pyface.qt.QtGui import QColor
from pyface.qt.QtWidgets import QStyledItemDelegate

class ColorRenderer(QStyledItemDelegate):
    def paint(self, painter, option, index):
        value = index.data()
        color = QColor(value)

        painter.save()

        # Draw the rectangle with the given color
        rect = option.rect
        painter.setBrush(color)
        painter.setPen(color)
        painter.drawRect(rect)

        painter.restore()

class ColorColumn(ObjectColumn): 
    def __init__(self, **traits): # Stolen from traitsui/extra/checkbox_column.py
        """Initializes the object."""
        super().__init__(**traits)

        # force the renderer to be our color renderer
        self.renderer = ColorRenderer()

layer_table_editor = TableEditor(
    columns=[
        ColorColumn(name='color', width=20, editable=False),
        ObjectColumn(name='name', label='Label', width=150, editable=False),
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