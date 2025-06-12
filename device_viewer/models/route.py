from traits.api import HasTraits, List, Int

# Abstract pathing object class
class Route():
    route = []

    def __init__(self, route: list[int]):
        self.route = route

    def can_add_segment(self, from_channel: int, to_channel: int):
        '''Returns if this path can accept a given segment'''
        # We can currently only add to the ends of routes
        return len(self.route) == 0 or from_channel == self.route[-1] or to_channel == self.route[0]
    
    def add_segment(self, from_channel: int, to_channel: int):
        '''Adds segment to path'''
        if len(self.route) == 0: # Path is empty
            self.route.append(from_channel)
            self.route.append(to_channel)
        elif to_channel == self.route[0]: # Append to start
            self.route.insert(0, to_channel)
        elif from_channel == self.path[-1]: # Append to end
            self.route.append(from_channel)

    def remove_segment(self, from_channel: int, to_channel: int):
        '''Returns a list of new routes (in no particular order) that result from removing a segment from a given path (and merging pieces). Object should be dereferenced afterwards'''
        if len(self.route) == 0:
            return [[]]
        
        new_routes = [[]] # Where route pieces are stored
        deleted_segment = (from_channel, to_channel)

        # First, we partition the route into the deleted segment and routes in between
        # Example: Deleting segment (1,2) for route 0-1-2-3-1-2-4-0
        # new_routes: [[0,1],[2,3,1],[2,4,0]]
        # Note that the order and count of channels do not change, so the first and last element being equal still indicates a loop
        for i in range(len(self.route)-1):
            new_routes[-1].append(self.route[i])

            cur_segment = (self.route[i], self.route[i+1])
            if cur_segment == deleted_segment or cur_segment == deleted_segment[::-1]: # Check both ways from -> to, to -> from
                # Terminate current segment and create new one
                new_routes.append([])
        new_routes[-1].append(self.route[-1]) # Add final element
        print(new_routes)

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

    def is_loop(self):
        '''Return True if the path is a loop'''
        return len(self.path) >= 2 and self.path[0] == self.path[-1]
    