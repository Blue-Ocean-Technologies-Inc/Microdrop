from queue import Queue
from typing import Any

from device_viewer.models.route import Route


def find_shortest_paths(from_id, neighbors: dict,existing_routes: list["Route"]=None, avoid_collisions=True) -> dict[Any, list]:
    # Run BFS using the stored neighbors/coordinates to get the shortest path (in terms of nodes) from from_id to all other nodes
    # Under the constraints that all nodes in valid paths are at least one neighbor away from any existing routes

    if avoid_collisions:
        blocked = generate_blocked_nodes_map(existing_routes, neighbors)
    else:
        blocked = {}

    # Now we do BFS from from_id, keeping track of path info too
    q = Queue()
    q.put(from_id)

    q2_set = set()

    visited = {from_id: True}
    paths = {from_id: [from_id]}  # Only contains valid paths. Not complete for all electrode ids, so used get()

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
                    paths[neighbor] = paths[current]  # Given boundary blocked nodes an initial path
                    # paths is expected to get assigned multiple times, and thus at the end gives us the longest optimal path 1 away from the boundry
                    # which is a good approxmiation 
                    q2_set.add(neighbor)  # add them for the next pass

    # Second pass - Propogate partial paths
    # This should touch all reachable nodes from from_id, assigning a partial path for when hovering on that node
    # The difference here is that we don't care about whether a found node is blocked anymore
    # Note that from the above loop, no blocked node is visited, so we can use 'visited' just fine
    q2 = Queue()
    for electrode_id in q2_set:  # We use a set since each blocked node can be 'add'ed many times (since its never marked as visited in first pass)
        q2.put(electrode_id)
        visited[electrode_id] = True

    while not q2.empty():
        current = q2.get()
        for neighbor in neighbors[current]:
            if not visited.get(neighbor, False):
                paths[neighbor] = paths[current]  # Propogate current partial path
                q2.put(neighbor)
                visited[neighbor] = True

    return paths


def generate_blocked_nodes_map(existing_routes: list[Route], neighbors: dict) -> dict[Any, Any]:
    # First, we generate the map of nodes we cannot visit.
    blocked = {}

    for route in existing_routes:
        for electrode_id in route.route:
            blocked[electrode_id] = True  # Every node
            for neighbor in neighbors[electrode_id]:
                blocked[neighbor] = True  # ...and its neighbors
    return blocked