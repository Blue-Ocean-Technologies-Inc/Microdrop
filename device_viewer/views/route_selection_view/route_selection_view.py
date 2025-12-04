from traitsui.api import View, VGroup, Item, ObjectColumn, TableEditor, Handler
from traitsui.ui import UIInfo

from device_viewer.views.route_selection_view.menu import RouteLayerMenu
from device_viewer.models.route import RouteLayer

from microdrop_utils.traitsui_qt_helpers import ColorColumn, VisibleColumn

class RouteLayerHandler(Handler):
    # For these handlers, info is as usual, and rows is a list of rows that the action is acting on
    # In the case of the right click menu, always a list of size 1 with the affected row

    def invert_layer(self, info: UIInfo, rows: list[RouteLayer]):
        rows[0].route.invert()
    
    def delete_layer(self, info, rows):
        info.object.delete_layer(rows[0])

    def start_merge_layer(self, info, rows):
        info.object.layer_to_merge = rows[0]
        info.object.mode = "merge"

    def merge_layer(self, info, rows): 
        if info.object.layer_to_merge == None: # Sanity check
            self.cancel_merge_route(info, rows)
            return

        info.object.merge_layer(rows[0])

    def cancel_merge_layer(self, info, rows):
        info.object.mode = "edit"


layer_table_editor = TableEditor(
    columns=[
        ObjectColumn(name='name', label="", resize_mode="stretch", editable=False),
        VisibleColumn(name='visible', label="", editable=False, horizontal_alignment='center', width=16)
    ],
    menu=RouteLayerMenu,
    show_lines=False,
    selected="selected_layer",
    sortable=False,
    reorderable=True,
    show_column_labels=False,
    show_row_labels=True,
)

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