from traits.api import HasTraits, List, Enum, Bool, Instance, String, observe, Str
import random
from queue import Queue
from collections import Counter
from microdrop_style.colors import PRIMARY_SHADE

# Abstract pathing object class
class Route(HasTraits):
    # Note that route should be able to be edited directly (i.e. layer.route = [1,2,3])
    route = List() # List of ids - ids can be anything! In this case they are most likely strings or ints though

    def _route_default(self):
        return []

    def __init__(self, route: list = [], channel_map={}, neighbors={}):
        self.route = route
        self.channel_map = channel_map
        self.neighbors = neighbors

    def get_channel_from_id(self, id):
        for key, value in self.channel_map.items():
            if id in value:
                return key
        return None

    def get_segments(self):
        '''Returns list of segments from current route'''
        return list(zip(self.route, self.route[1:]))

    def get_endpoints(self):
        '''Returns a list of endpoints or the empty list'''
        if len(self.route) == 0:
            return []
        else:
            return [self.route[0], self.route[-1]]        

    def is_loop(self):
        '''Return True if the path is a loop'''
        return len(self.route) >= 2 and self.route[0] == self.route[-1]
    
    def count_loops(self):
        '''Count how many times a path loops'''
        return self.route.count(self.route[0])-1
    
    def get_name(self):
        if len(self.route) == 0:
            return "Empty route"
        elif self.is_loop():
            loop_count = self.count_loops()
            if loop_count > 1:
                return f"{loop_count}x loop at {self.get_channel_from_id(self.route[0])}"
            else:
                return f"Loop at {self.get_channel_from_id(self.route[0])}"
        else:
            return f"Path from {self.get_channel_from_id(self.route[0])} to {self.get_channel_from_id(self.route[-1])}"

    @staticmethod
    def is_segment(from_a, to_a, from_b, to_b):
        '''Returns if segment a is equivalent to segment b (equal or equal reversed)'''
        return (from_a == from_b and to_a == to_b) or (from_a == to_b and to_a == from_b)
    
    def has_segment(self, from_id, to_id):
        '''Checks if the route has a particular segment'''
        for i in range(len(self.route)-1):
            if Route.is_segment(from_id, to_id, self.route[i], self.route[i+1]):
                return True
        return False
    
    def can_add_segment(self, from_id, to_id):
        '''Returns if this path can accept a given segment'''
        # We can currently only add to the ends of routes
        if len(self.route) == 0:
            return True
        
        endpoints = (self.route[-1], self.route[0])
        return from_id in endpoints or to_id in endpoints
    
    def can_merge(self, other: "Route"):
        '''Returns if other can be merged with the current route'''
        return bool(set(self.get_endpoints()) & set(other.get_endpoints())) # Juct check for endpoint overlap
    
    def merge(self, other: "Route"):
        '''Merge with other route. Does this in place and does not modify the other route. Prioritizes putting other at end in ambigous cases. Assumes can_merge returns True'''
        if self.route[-1] == other.route[0]:
            self.route = self.route + other.route[1:]
        elif self.route[0] == other.route[-1]:
            self.route = other.route[:-1] + self.route

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

    def can_remove(self, from_id, to_id):
        '''Returns true if the segment (from_id, to_id) can be removed'''
        return (from_id, to_id) in self.get_segments()

    def remove_segment(self, from_id, to_id):
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
    
    @staticmethod
    def find_shortest_paths(from_id, existing_routes: list["Route"], neighbors: dict) -> list:
        # Run BFS using the stored neighbors/coordinates to get the shortest path (in terms of nodes) from from_id to all other nodes
        # Under the constraints that all nodes in valid paths are at least one neighbor away from any existing routes
        
        # First, we generate the map of nodes we cannot visit.
        blocked = {}

        for route in existing_routes:
            for electrode_id in route.route:
                blocked[electrode_id] = True # Every node
                for neighbor in neighbors[electrode_id]:
                    blocked[neighbor] = True # ...and its neighbors
        
        # Now we do BFS from from_id, keeping track of path info too
        q = Queue()
        q.put(from_id)

        q2_set = set()

        visited = {from_id: True}
        paths = {from_id: [from_id]} # Only contains valid paths. Not complete for all electrode ids, so used get()

        # First pass - Generate all possible valid paths
        while not q.empty():
            current = q.get()
            for neighbor in neighbors[current]:
                if not visited.get(neighbor, False):
                    neighbor_blocked = blocked.get(neighbor, False)
                    if not neighbor_blocked:
                        paths[neighbor] = paths[current] + [neighbor]
                        q.put(neighbor)
                        visited[neighbor] = True
                    else:
                        paths[neighbor] = paths[current] # Given boundary blocked nodes an initial path
                        # paths is expected to get assigned multiple times, and thus at the end gives us the longest optimal path 1 away from the boundry
                        # which is a good approxmiation 
                        q2_set.add(neighbor) # add them for the next pass

        # Second pass - Propogate partial paths
        # This should touch all reachable nodes from from_id, assigning a partial path for when hovering on that node
        # The difference here is that we don't care about whether a found node is blocked anymore
        # Note that from the above loop, no blocked node is visited, so we can use 'visited' just fine
        q2 = Queue()
        for electrode_id in q2_set: # We use a set since each blocked node can be 'add'ed many times (since its never marked as visited in first pass)
            q2.put(electrode_id)
            visited[electrode_id] = True

        while not q2.empty():
            current = q2.get()
            for neighbor in neighbors[current]:
                if not visited.get(neighbor, False):
                    paths[neighbor] = paths[current] # Propogate current partial path
                    q2.put(neighbor)
                    visited[neighbor] = True
        
        return paths
        

    def invert(self):
        self.route.reverse()
    
    def __repr__(self):
        return f"<Route path={self.route}>"

class RouteLayer(HasTraits):
    visible = Bool(True)
    name = String()
    
    # These traits are direct derivatives from a RouteLayerManager traits. Do not modify from the Layer itself, only read
    is_selected = Bool(False) # Needed to show selectedness in the TableEditor
    merge_in_progress = Bool(False)

    # Needs to be passed
    route = Instance(Route) # Actual route model
    color = String() # String that can be passed to QColor
    
    def _name_default(self):
        return self.route.get_name()

    @observe("route.route.items")
    def _route_path_updated(self, event):
        self.name = self.route.get_name()

    def __repr__(self) -> str:
        return f"<RouteLayer route={self.route} name={self.name}>"

class RouteLayerManager(HasTraits):
    # ---------------- Model Traits -----------------------
    layers = List(RouteLayer, [])

    selected_layer = Instance(RouteLayer)

    layer_to_merge = Instance(RouteLayer)

    mode = Enum("draw", "edit", "auto", "merge")

    message = Str("")

    # --------------------------- Model Helpers --------------------------
    
    def get_available_color(self):
        color_counts = {}
        shades = [300, 800, 400, 700, 500, 600] 
        for shade in shades:
            color = PRIMARY_SHADE[shade]
            color_counts[color] = 0
        for layer in self.layers:
            if layer.color in color_counts.keys():
                color_counts[layer.color] += 1
        return Counter(color_counts).most_common()[-1][0] # Return least common color
    
    def replace_layer(self, old_route_layer: RouteLayer, new_routes: list[Route]):
        index = self.layers.index(old_route_layer)
        self.layers.pop(index) # Delete the current layer

        for i in range(len(new_routes)): # Add in new routes in the same place the old route was, so a new route is preselected
            if i == 0: # Maintain color of old route for the case of 1 returned, visual persisitance
                self.add_layer(new_routes[i], index, old_route_layer.color)
            else:
                self.add_layer(new_routes[i], index)

        if index < len(self.layers):
            self.selected_layer = self.layers[index]
        elif len(self.layers) == 0:
            self.selected_layer = None
            self.mode = 'draw' # Nothing to edit, so set to draw
        else:
            self.selected_layer = self.layers[-1] # Set it to the last layer

    def delete_layer(self, layer: RouteLayer):
        self.replace_layer(layer, [])

    def add_layer(self, route: Route, index=None, color=None):
        if color == None:
            color = self.get_available_color()
        if index == None:
            self.layers.append(RouteLayer(route=route, color=color))
        else:
            self.layers.insert(index, RouteLayer(route=route, color=color))

    def reset(self):
        self.layers = []
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
        if self.selected_layer == None and hasattr(event, "new") and len(event.new) > 0: # If we have no routes and a route is added, select it
            self.selected_layer = event.new[0]
    
    @observe('selected_layer')
    def _selected_layer_changed(self, event):
        # Mark only the selected layer
        for layer in self.layers:
            layer.is_selected = (layer is event.new)

    @observe('layer_to_merge')
    def _layer_to_merge_changed(self, event):
        for layer in self.layers:
            layer.merge_in_progress = (event.new != None)

