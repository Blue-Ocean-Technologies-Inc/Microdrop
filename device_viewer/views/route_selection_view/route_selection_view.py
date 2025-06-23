from traitsui.api import View, VGroup, HGroup, ButtonEditor, Editor, Item, ObjectColumn, TableEditor, Label, Handler, Action
from traitsui.extras.checkbox_column import CheckboxColumn
from traitsui.ui import UIInfo
from traits.api import Button
from pyface.qt.QtGui import QColor
from pyface.qt.QtWidgets import QStyledItemDelegate

from device_viewer.views.route_selection_view.menu import RouteLayerMenu
from device_viewer.models.route import RouteLayer

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
    menu=RouteLayerMenu,
    show_lines=False,
    selected="selected_layer",
    sortable=False,
    editable=True,
    reorderable=True
)

class RouteLayerHandler(Handler):
    # For these handlers, info is as usual, and rows is a list of rows that the action is acting on
    # In the case of the right click menu, always a list of size 1 with the affected row

    def invert_layer(self, info: UIInfo, rows: list[RouteLayer]):
        rows[0].route.invert()
    
    def delete_layer(self, info, rows):
        info.object.replace_layer(rows[0], []) # Just delete row

    def start_merge_layer(self, info, rows):
        info.object.layer_to_merge = rows[0]
        info.object.message = "Route merging: " + rows[0].route.get_name()

    def merge_layer(self, info, rows): 
        if info.object.layer_to_merge == None: # Sanity check
            self.cancel_merge_route(info, rows)
            return

        selected_route = rows[0].route
        route_to_merge = info.object.layer_to_merge.route
        if route_to_merge.can_merge(selected_route) and selected_route != route_to_merge:
            route_to_merge.merge(selected_route)
            info.object.message = "Route merging: " + selected_route.get_name()
            self.delete_layer(info, rows) # Delete selected route

    def cancel_merge_layer(self, info, rows):
        info.object.layer_to_merge = None
        info.object.message = ""

# Width for the whole table needs to be set in the widget itself (in the pane's create_contents)
RouteLayerView = View(
        VGroup(
            Item('message', style='readonly', show_label=False),
            Item('layers', editor=layer_table_editor, show_label=False)
        ),
        resizable=True,
        title="Route Layer Selector",
        handler=RouteLayerHandler,
)