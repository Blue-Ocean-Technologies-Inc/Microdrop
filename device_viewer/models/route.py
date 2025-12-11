from traits.api import HasTraits, List, Enum, Bool, Instance, observe, Str
from collections import Counter
from ..default_settings import ROUTE_COLOR_POOL

# Abstract pathing object class
class Route(HasTraits):
    # Note that route should be able to be edited directly (i.e. layer.route = [1,2,3])
    route = List() # List of ids - ids can be anything! In this case they are most likely strings or ints though

    def _route_default(self):
        return []

    def get_channel_from_id(self, id, channel_map):
        for key, value in channel_map.items():
            if id in value:
                return key
        return None

    def get_segments(self) -> list[tuple]:
        '''Returns list of segments from current route'''
        return list(zip(self.route, self.route[1:]))

    def get_endpoints(self):
        '''Returns a list of endpoints or the empty list'''
        if len(self.route) == 0:
            return []
        else:
            return [self.route[0], self.route[-1]]        

    def is_loop(self) -> bool:
        '''Return True if the path is a loop'''
        return len(self.route) >= 2 and self.route[0] == self.route[-1]

    def count_loops(self) -> int:
        '''Count how many times a path loops'''
        return self.route.count(self.route[0])-1

    def get_name(self, channel_map: dict[int, list]) -> str:
        # channel_map is a map of channel id to list of electrode ids
        if len(self.route) == 0:
            return "Empty route"
        elif self.is_loop():
            loop_count = self.count_loops()
            if loop_count > 1:
                return f"{loop_count}x loop @ {self.get_channel_from_id(self.route[0], channel_map)}"
            else:
                return f"Loop @ {self.get_channel_from_id(self.route[0], channel_map)}"
        else:
            return f"Path: {self.get_channel_from_id(self.route[0], channel_map)} -> {self.get_channel_from_id(self.route[-1], channel_map)}"

    @staticmethod
    def is_segment(from_a, to_a, from_b, to_b) -> bool:
        '''Returns if segment a is equivalent to segment b (equal or equal reversed)'''
        return (from_a == from_b and to_a == to_b) or (from_a == to_b and to_a == from_b)
    
    def has_segment(self, from_id, to_id):
        '''Checks if the route has a particular segment'''
        for i in range(len(self.route)-1):
            if Route.is_segment(from_id, to_id, self.route[i], self.route[i+1]):
                return True
        return False
    
    def can_add_segment(self, from_id, to_id) -> bool:
        '''Returns if this path can accept a given segment'''
        # We can currently only add to the ends of routes
        if len(self.route) == 0:
            return True
        
        endpoints = self.get_endpoints()
        return to_id == endpoints[0] or from_id in self.route
    
    def can_merge(self, other: "Route") -> bool:
        '''Returns if other can be merged with the current route'''
        self_endpoints = self.get_endpoints()
        other_endpoints = other.get_endpoints()
        return self_endpoints[0] == other_endpoints[1] or self_endpoints[1] == other_endpoints[0]
    
    def merge(self, other: "Route") -> list:
        '''Merge with other route. Does this in place and does not modify the other route. Prioritizes putting other at end in ambigous cases. Assumes can_merge returns True'''
        if self.route[-1] == other.route[0]:
            return self.route + other.route[1:]
        elif self.route[0] == other.route[-1]:
            return other.route[:-1] + self.route

    def add_segment(self, from_id, to_id):
        '''Adds segment to path'''
        # The order of these cases is *very* important! We prioritize appending to end and in-direction, in that order!
        # Changing the order will add the segment in a technically valid but strange place
        if len(self.route) == 0: # Path is empty
            self.route.append(from_id)
            self.route.append(to_id)
        elif from_id == self.route[-1]: # Append to end, in-direction
            self.route.append(to_id)
        elif to_id == self.route[0]: # Append to start, in-direction
            self.route.insert(0, from_id)
        elif from_id == self.route[0]: # Append to start, out-of-direction
            # We want it so that extending a path in the opposite direction
            # that its going still expands it, but in the right direction
            self.route.insert(0, to_id)
        else:
            # We're extending from the middle! We actually add 2 segments: the segment and its reverse,
            # and use it to extend every part of the path that has from_id
            new_route = []
            for electrode_id in self.route:
                new_route.append(electrode_id)
                if electrode_id == from_id:
                    new_route.append(to_id)
                    new_route.append(from_id)
            
            self.route = new_route

    def can_remove(self, from_id, to_id) -> bool:
        '''Returns true if the segment (from_id, to_id) can be removed'''
        return (from_id, to_id) in self.get_segments()

    def remove_segment(self, from_id, to_id) -> list[list]:
        '''Returns a list of new routes (in no particular order) that result from removing a segment from a given path (and merging pieces). Object should be dereferenced afterwards'''
        if len(self.route) == 0:
            return [[]]
        
        new_routes = [[]] # Where route pieces are stored

        # First, we partition the route into the deleted segment and routes in between
        # Example: Deleting segment (1,2) for route 0-1-2-3-1-2-4-0
        # new_routes: [[0,1],[2,3,1],[2,4,0]]
        # Note that the order and count of channels do not change, so the first and last element being equal still indicates a loop
        for i in range(len(self.route)-1):
            new_routes[-1].append(self.route[i])
            if Route.is_segment(from_id, to_id, self.route[i], self.route[i+1]): # Check both ways from -> to, to -> from
                # Terminate current segment and create new one
                new_routes.append([])
        new_routes[-1].append(self.route[-1]) # Add final element

        # Now we do the merge phase. We'll merge (concatonate) new_routes A and B on the following conditions:
        # 1. B is the closest mergable with A *after it* in the list (with loopbacks)
        #    - This is to try to preserve general order as best as possible
        # 2. The endpoint of A is the starting point of B
        # We keep trying to merge the merged routes until not possible, then output
        merge_flag = True
        while merge_flag:
            merge_flag = False
            for i in range(len(new_routes)):
                if len(new_routes[i]) == 0: continue
                for offset in range(len(new_routes)-1): # Look for closest possible merge
                    j = (i+1+offset)%len(new_routes) # Add offest and loop around
                    if len(new_routes[j]) == 0: continue
                    if new_routes[i][-1] == new_routes[j][0]: # If condition 2 is met, merge
                        new_routes[i] = new_routes[i] + new_routes[j][1:]
                        new_routes[j] = [] # We cant delete anything since it would break our loops
                        merge_flag = True
                        break
            
        return list(filter(lambda route: len(route) > 1, new_routes)) # Remove empty/singular routes

    def invert(self):
        self.route.reverse()
    
    def __repr__(self) -> str:
        return f"<Route path={self.route}>"

class RouteLayer(HasTraits):
    visible = Bool(True)
    
    # These traits are direct derivatives from a RouteLayerManager traits. Do not modify from the Layer itself, only read
    is_selected = Bool(False) # Needed to show selectedness in the TableEditor
    merge_in_progress = Bool(False)

    # Needs to be passed
    route = Instance(Route, Route()) # Actual route model
    color = Str("red") # String that can be passed to QColor

    # set name based on channels for electrodes if needed for UI
    name = Str("")

    def __repr__(self) -> str:
        return f"<RouteLayer route={self.route} name={self.name}>"

class RouteLayerManager(HasTraits):
    # ---------------- Model Traits -----------------------
    layers = List(RouteLayer, [])

    selected_layer = Instance(RouteLayer)

    layer_to_merge = Instance(RouteLayer)

    autoroute_layer = Instance(RouteLayer)

    message = Str

    mode = Enum("draw", "edit", "merge")
    # --------------------------- Model Helpers --------------------------

    def get_available_color(self, exclude=()):
        color_counts = {}
        color_pool = ROUTE_COLOR_POOL
        for color in color_pool + exclude:
            color_counts[color] = 0
        for layer in self.layers:
            if layer.color in color_counts.keys():
                color_counts[layer.color] += 1
        return Counter(color_counts).most_common()[-1][0] # Return least common color
    
    def replace_layer(self, old_route_layer: RouteLayer, new_routes: list[Route]):
        index = self.layers.index(old_route_layer)

        layers_to_add = []
        for i in range(len(new_routes)): # Add in new routes in the same place the old route was, so a new route is preselected
            if i == 0: # Maintain color of old route for the case of 1 returned, visual persistence
                layers_to_add.append(RouteLayer(route=new_routes[i], color=old_route_layer.color))
            else:
                new_colors = tuple([layer.color for layer in layers_to_add])
                layers_to_add.append(RouteLayer(route=new_routes[i], color=self.get_available_color(exclude=new_colors)))

        self.layers[index:index+1] = reversed(layers_to_add) # Delete and replace in single operation for easy undo

        if index < len(self.layers):
            self.selected_layer = self.layers[index]
    
        return index

    def delete_layer(self, layer: RouteLayer):
        self.layers.remove(layer)

    def add_layer(self, route: Route, index=None, color=None):
        if color == None:
            color = self.get_available_color()
        if index == None:
            self.layers.append(RouteLayer(route=route, color=color))
        else:
            self.layers.insert(index, RouteLayer(route=route, color=color))

    def merge_layer(self, other_layer) -> bool:
        '''Try to merge other_layer with layer_to_merge. Returns boolean indicating operation's success'''
        if self.layer_to_merge.route.can_merge(other_layer.route):
            new_route = Route(route=self.layer_to_merge.route.merge(other_layer.route))
            index = self.replace_layer(self.layer_to_merge, [new_route]) # This should set layer_to_merge to None (for consistency) and mode to something else
            self.layer_to_merge = self.layers[index] # ...so set it back
            self.mode = 'merge'
            self.delete_layer(other_layer)
            return True
        else:
            return False

    def clear_routes(self):
        self.layers.clear()
        self.selected_layer = None
        self.layer_to_merge = None
        self.mode = "draw"
        self.message = ""

    def get_route(self, index: int):
        if 0 <= index < len(self.layers):
            return self.layers[index].route
        else:
            return None
        
    def get_selected_route(self):
        if self.selected_layer:
            return self.selected_layer.route
        else:
            return None
    
    # --------------------- Observers ------------------------------
    @observe('layers.items')
    def _layers_items_changed(self, event):
        if self.layer_to_merge is not None and self.layer_to_merge not in self.layers: # Clean up merge reference
            self.layer_to_merge = None
            self.mode = "edit"
        
        if self.selected_layer not in self.layers: # Clean up selected reference
            if len(self.layers) == 0:
                self.selected_layer = None
                self.mode = 'draw' # Nothing to edit, so set to draw
            else:
                self.selected_layer = self.layers[-1] # Set it to the last layer
    
    @observe('selected_layer')
    @observe('layers.items')
    def update_selected_layers(self, event):
        # Mark only the selected layer
        for layer in self.layers:
            layer.is_selected = (layer is self.selected_layer)

    @observe('layer_to_merge')
    @observe('layer_to_merge.name')
    def _layer_to_merge_changed(self, event):
        if event.name == "layer_to_merge": # event.new is the layer
            for layer in self.layers:
                layer.merge_in_progress = (event.new != None)
            if event.new:
                self.message = f"Route merging: {event.new.name}"
        elif event.name == "name": # event.new is the new name
            self.message = f"Route merging: {event.new}"