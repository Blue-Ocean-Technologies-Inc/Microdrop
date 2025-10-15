import numpy as np
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree
from collections import defaultdict
# np.random.seed(42)

# vertices for a square polygon
v1 = [1., 1.]
v2 = [2., 1.]
v3 = [2., 0.]
v4 = [1., 0.]

_centers = np.array([v1, v2, v3, v4]) # square. points sep by 1 unit.

_lines_names = [
    "v1-v2",
    "v2-v3",
    "v3-v4",
    "v1-v4",
    "v1-v3",
    "v2-v4"
]

# --- 2. Define Polygon Properties ---
side_length = 0.8  # The side length for each square
_polygons = []
_polygon_names = {}

# --- 3. Construct the Polygons around Center---
# Iterate through each center point to create a square
for i, center in enumerate(_centers):
    cx, cy = center
    h = side_length / 2.0  # Half of the side length

    # Calculate the four corner coordinates of the square
    base_corners = [
        (cx - h, cy - h),  # Bottom-left
        (cx + h, cy - h),  # Bottom-right
        (cx + h, cy + h),  # Top-right
        (cx - h, cy + h)   # Top-left
    ]

    # Perturb each corner by adding random noise
    irregular_corners = []
    irregularity = side_length / 4 # How much the corners can be moved. 0=perfect square.
    for x, y in base_corners:
        noise_x = np.random.uniform(-irregularity, irregularity)
        noise_y = np.random.uniform(-irregularity, irregularity)
        irregular_corners.append((x + noise_x, y + noise_y))

    #Create the Shapely Polygon object and add it to our list
    # square = Polygon(base_corners)
    # polygons.append(square)
    # polygon_names[f"{square}"] = f"v{i + 1}"

    # Create the Shapely Polygon object
    irregular_square = Polygon(irregular_corners)

    _polygons.append(irregular_square)
    _polygon_names[f"{irregular_square}"] = f"v{i + 1}"

# for el in polygons:
#   display(el)

print("-"*1000)
print(_polygons)
print("-"*1000)

# add noise and find new threshold
# 6 lines for a square. Includes diagonal connections.
_lines = np.array(
    [
        v1 + v2,
         v2 + v3,
         v3 + v4,
         v4 + v1,
         v1 + v3,
         v2 + v4
    ]
)

scale = side_length / 4

_line_startpoint_coords = _lines[..., 0:2]
_line_endpoint_coords = _lines[..., 2:4]

# add noise to the lines
_noise = np.random.normal(0, scale, size=_line_startpoint_coords.shape)
_line_startpoint_coords += _noise
_noise = np.random.normal(0, scale, size=_line_endpoint_coords.shape)
_line_endpoint_coords += _noise

# get shapely Points for the line endpoints
_line_startpoints = [Point(x, y) for x, y in _line_startpoint_coords]
_line_endpoints = [Point(x, y) for x, y in _line_endpoint_coords]
_line_points = _line_startpoints + _line_endpoints

class Util:

    def __init__(self, polygons, line_points, line_names, polygon_names):

        self.polygons = polygons
        self.polygon_names = polygon_names

        self.line_points = line_points
        self.line_names = line_names

        # construct the STRTree (Sort-Tile-Recursive Tree)
        # (https://shapely.readthedocs.io/en/2.1.1/strtree.html)
        self.tree = STRtree(self.polygons)

        self.line_polygon_mapping = self.get_line_polygon_mapping()


    def get_line_polygon_mapping(self):
        # Find the nearest tree geometries to the input geometries
        line_query = self.tree.query_nearest(self.line_points)

        print("-"*1000)
        print(list(zip(line_query.take(line_query[0]), self.tree.geometries.take(line_query[1]))))
        print("-"*1000)

        res_dict = defaultdict(set)

        # transpose to get all pairs of input and tree indices
        for line_point_idx, polygon_idx in line_query.T.tolist():
          # modulo returned indices to match indexing of lines
          line_name = self.line_names[line_point_idx % len(self.line_names)]
          poly_name = self.polygon_names[f"{self.polygons[polygon_idx]}"]

          res_dict[line_name].add(poly_name)

        print("-"*1000)
        print(res_dict)
        print("-"*1000)

        return res_dict


# check validity

expected = defaultdict(set,
            {'v1-v2': {'v1', 'v2'},
             'v2-v3': {'v2', 'v3'},
             'v3-v4': {'v3', 'v4'},
             'v1-v4': {'v1', 'v4'},
             'v1-v3': {'v1', 'v3'},
             'v2-v4': {'v2', 'v4'}})

util = Util(
    polygons=_polygons,
    line_points=_line_points,
    line_names=_lines_names,
    polygon_names=_polygon_names
)

res_dict = util.line_polygon_mapping

for key in res_dict:
    if sorted(res_dict[key]) != sorted(expected[key]):
        print(res_dict[key])
        print(expected[key])

        print(util.line_points)

        raise Exception(f"{key} not in {expected}")

print("Valid")