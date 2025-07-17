from typing import Any
from traitsui.api import View, VGroup, Item, ObjectColumn, TableEditor, Label, Handler, Action
from traitsui.extras.checkbox_column import CheckboxColumn
from traitsui.ui import UIInfo
from pyface.qt.QtGui import QColor, QFont
from pyface.qt.QtWidgets import QStyledItemDelegate

from device_viewer.views.route_selection_view.menu import RouteLayerMenu
from device_viewer.models.route import RouteLayer
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_VISIBILITY, ICON_VISIBILITY_OFF

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

class VisibleColumn(ObjectColumn):
    def __init__(self, **traits: Any):
        super().__init__(**traits)
        self.format_func = self.formatter
        self.text_font = QFont(ICON_FONT_FAMILY, 15)

    def formatter(self, value): # No self since were just passing it as a function
        return ICON_VISIBILITY if value else ICON_VISIBILITY_OFF
    
    def on_click(self, object):
        object.visible = not object.visible

layer_table_editor = TableEditor(
    columns=[
        ColorColumn(name='color', width=20, editable=False),
        ObjectColumn(name='name', label='Label', resize_mode="stretch", editable=False),
        VisibleColumn(name='visible', editable=False, horizontal_alignment='center', width=20),
    ],
    menu=RouteLayerMenu,
    show_lines=False,
    selected="selected_layer",
    sortable=False,
    reorderable=True
)

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