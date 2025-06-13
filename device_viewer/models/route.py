from traits.api import HasTraits, List, Int

# Abstract pathing object class
class Route(HasTraits):
    route = List()

    def _route_default(self):
        return []

    def __init__(self, route: list = []):
        self.route = route

    def get_segments(self):
        '''Returns list of segments from current route'''
        return list(zip(self.route, self.route[1:]))

    def is_loop(self):
        '''Return True if the path is a loop'''
        return len(self.route) >= 2 and self.route[0] == self.route[-1]

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
    
    def add_segment(self, from_id, to_id):
        '''Adds segment to path'''

        print(self.route, f", gotten segment: {from_id, to_id}")

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

        print(self.route)
        

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
    
    def __repr__(self):
        return f"<Route path={self.route}>"
