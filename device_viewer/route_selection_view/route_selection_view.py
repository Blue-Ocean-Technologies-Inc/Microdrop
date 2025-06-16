from traitsui.api import View, Group, Item, BasicEditorFactory, Controller, TableEditor, ObjectColumn
from traitsui.extras.checkbox_column import CheckboxColumn
from traits.api import HasTraits, List, Int, Bool, Instance
from pyface.qt.QtGui import QColor

layer_table_editor = TableEditor(
    columns=[
        ObjectColumn(name='name', label='Layer Name', width=150),
        CheckboxColumn(name='visible', label='Visible', width=50),
    ],
    editable=True,
    deletable=True,
    sortable=True,
    reorderable=True,  # Only works in wx backend
)

# Width for the whole table needs to be set in the widget itself (in the pane's create_contents)
RouteLayerView = View(
        Item('layers', editor=layer_table_editor, show_label=False), 
        resizable=True,
        title="Layer Selector Example"
)

class RouteLayer(HasTraits):
    index = Int(0)
    visibility = Bool(True)
    color = Instance(QColor)

    @property
    def name(self):
        return "Apples"

class RouteLayerManager(HasTraits):
    layers = List(RouteLayer)

    def _layers_default(self):
        return [RouteLayer(color=QColor("red"))]