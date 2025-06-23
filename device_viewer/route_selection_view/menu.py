from traits.api import HasTraits, List, Str, Instance
from traitsui.api import View, TableEditor, ObjectColumn, Handler
from traitsui.menu import Menu, Action
from traitsui.ui import UIInfo

from device_viewer.models.route import RouteLayer
from microdrop_utils.status_bar_utils import set_status_bar_message, clear_status_bar_message

class RouteLayerMenuHandler(Handler):
    # For these handlers, info is as usual, and rows is a list of rows that the action is acting on
    # In the case of the right click menu, always a list of size 1 with the affected row
    def invert_layer(self, info: UIInfo, rows: list[RouteLayer]):
        rows[0].route.invert()
    
    def delete_layer(self, info, rows):
        info.object.replace_layer(rows[0], []) # Just delete row

    def start_merge_layer(self, info, rows):
        info.object.layer_to_merge = rows[0]
        window = info.ui.context.get('window') # This context is custom defined in the dock pane's create_contents
        if window:
            set_status_bar_message("Select route to merge with", window, 0)

    def end_merge_layer(self, info, rows): 
        if info.object.layer_to_merge == None: # Sanity check
            self.cancel_merge_route(info, rows)
            return

        selected_route = rows[0].route
        route_to_merge = info.object.layer_to_merge.route
        if route_to_merge.can_merge(selected_route):
            route_to_merge.merge(selected_route)
            self.delete_layer(info, rows) # Delete selected route
            self.cancel_merge_layer(info, rows) # Remove the message and reset layer_to_merge

    def cancel_merge_layer(self, info, rows):
        info.object.layer_to_merge = None
        window = info.ui.context.get('window')
        if window:
            clear_status_bar_message(window)
 
RouteLayerMenu = Menu(
    Action(name="Invert", action="invert_layer"),
    Action(name="Delete", action="delete_layer"),
    Action(name="Start Merge", action="start_merge_layer", visible_when="not object.merge_in_progress"), # Note that object in this case refers to the RouteLayer clicked on! No easy way to access main model
    Action(name="Finalize Merge", action="end_merge_layer", visible_when="object.merge_in_progress"),
    Action(name="Cancel Merge", action="cancel_merge_layer", visible_when="object.merge_in_progress")
)