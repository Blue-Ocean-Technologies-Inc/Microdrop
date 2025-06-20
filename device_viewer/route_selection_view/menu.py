from traits.api import HasTraits, List, Str, Instance
from traitsui.api import View, TableEditor, ObjectColumn, Handler
from traitsui.menu import Menu, Action
from traitsui.ui import UIInfo

from device_viewer.models.route import RouteLayer

class RouteLayerMenuHandler(Handler):
    # For these handlers, info is as usual, and rows is a list of rows that the action is acting on
    # In the case of the right click menu, always a list of size 1 with the affected row
    def invert_route(self, info: UIInfo, rows: list[RouteLayer]):
        rows[0].route.invert()
    
    def delete_route(self, info, rows):
        info.object.replace_layer(rows[0], []) # Just delete row

    def merge_route(self, info, rows):
        pass

RouteLayerMenu = Menu(
    Action(name="Invert", action="invert_route"),
    Action(name="Delete", action="delete_route"),
    Action(name="Merge", actoin="merge_route")
)