from xml.etree import ElementTree as ET

import numpy as np
from shapely.geometry import Polygon, LineString
from shapely.strtree import STRtree
from collections import defaultdict

from microdrop_utils._logger import get_logger

logger = get_logger(__name__, "INFO")

class LinePolygonTreeQueryUtil:
    """Class using STR Tree queries to find what polygons are intersecting with lines."""

    def __init__(self, polygons, lines, polygon_names, line_names):
        """
        Args:
            polygons (iterable): list of shapely.geometry.Polygons
            lines (iterable): list of shapely.geometry.LineStrings.
            polygon_names (list): list of polygon names. Should match indexing of polygons.
            line_names  (list): list of shapely.geometry.Polygon. Should match indexing of number of lines.
        """
        
        self.polygons = polygons
        self.polygon_names = polygon_names

        self.lines = [LineString(line.reshape((2,2))) for line in lines]
        self.line_names = line_names

        self.line_polygon_mapping = self.get_line_polygon_mapping()

    def get_line_polygon_mapping(self, max_attempts=10, buffer_factor=128):
        # Find the nearest tree geometries to the input geometries
        # construct the STRTree (Sort-Tile-Recursive Tree: https://shapely.readthedocs.io/en/2.1.1/strtree.html)
        # continue query with changing buffer sizes until we get only 2 hits for each line max attempts times.
        
        polygons = self.polygons
        logger.debug(f"Attempt 0/{max_attempts} with no buffer factor to get line polygons")
        for attempt in range(max_attempts):
            tree = STRtree(polygons)
            line_query = tree.query(self.lines, 'intersects')

            lines_have_2_polygons = np.all(np.unique(line_query[0], return_counts=1)[1] == 2)

            if lines_have_2_polygons:

                logger.debug(f"SUCCESS: {attempt}/{max_attempts}")

                logger.debug("-"*1000)
                logger.debug(list(zip(line_query.take(line_query[0]), tree.geometries.take(line_query[1]))))
                logger.debug("-"*1000)

                mapping = {name: set() for name in self.polygon_names}

                for i in range(len(self.lines)):
                    polygons_line_i = line_query[1, line_query[0] == i]

                    polygon_names_i = [
                        self.polygon_names[polygons_line_i[i]]
                        for i in range(len(polygons_line_i))
                    ]

                    mapping[polygon_names_i[0]].add(polygon_names_i[1])
                    mapping[polygon_names_i[1]].add(polygon_names_i[0])

                logger.debug("-"*1000)
                logger.debug(mapping)
                logger.debug("-"*1000)

                # convert values to list and return
                return  {key: list(val) for key, val in mapping.items()}

            else:
                polygons = [poly.buffer(poly.area / buffer_factor) for poly in polygons]
                logger.debug(f"Attempt {attempt+1}/{max_attempts} with buffer factor ~ {buffer_factor / (attempt + 1)} to get line polygons")

        raise ValueError(f"Could not find a solution with each line having only 2 polygons after {max_attempts} attempts.")


def channels_to_svg(old_filename, new_filename, electrode_ids_channels_map: dict[str, int], scale: float):
    tree = ET.parse(old_filename)
    root = tree.getroot()

    electrodes = None
    for child in root:
        if "Device" in child.attrib.values():
            electrodes = child
        elif child.tag == "{http://www.w3.org/2000/svg}metadata":
            scale_element = child.find("scale")
            if scale_element is None:
                scale_element = ET.SubElement(child, "scale")

            scale_element.text = str(scale)

    if electrodes is None:
        return

    for electrode in list(electrodes):
        channel = electrode_ids_channels_map[electrode.attrib["id"]]
        if channel is not None:
            electrode.attrib["data-channels"] = str(channel)
        else:
            electrode.attrib.pop("data-channels", None)

    ET.indent(root, space="  ")

    tree.write(new_filename)


def create_adjacency_dict(neighbours) -> dict:
    """
    Converts list of source-target pairs into an adjacency dictionary.

    Args:
        df (pd.DataFrame): DataFrame with 'source' and 'target' columns.

    Returns:
        dict: A dictionary where keys are IDs and values are lists of
              connected IDs, with no duplicates.
    """
    # Use a defaultdict to automatically handle the creation of new keys.
    adj_dict = defaultdict(list)

    # Iterate through each connection (row) in the DataFrame.
    for pairs in neighbours:
        # check if we have pairs, if not skip:
        if len(pairs) == 2:
            source = pairs[0]
            target = pairs[1]

            # Add the connection in both directions to capture the pairing.
            adj_dict[source].append(target)
            adj_dict[target].append(source)
        else:
            logger.debug(f"Skipping {pairs} due lack of elements.")

    # Remove duplicates from the lists by converting to a set and back.
    for key in adj_dict:
        adj_dict[key] = sorted(list(set(adj_dict[key])))

    # Return the result as a standard dictionary.
    return dict(adj_dict)


if __name__ == "__main__":

    # np.random.seed(42)

    # vertices for a square polygon
    v1 = [1., 1.]
    v2 = [2., 1.]
    v3 = [2., 0.]
    v4 = [1., 0.]

    _centers = np.array([v1, v2, v3, v4])  # square. points sep by 1 unit.

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
    _polygon_names = []

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
            (cx - h, cy + h)  # Top-left
        ]

        # # Perturb each corner by adding random noise
        # irregular_corners = []
        # irregularity = side_length / 4  # How much the corners can be moved. 0=perfect square.
        # for x, y in base_corners:
        #     noise_x = np.random.uniform(-irregularity, irregularity)
        #     noise_y = np.random.uniform(-irregularity, irregularity)
        #     irregular_corners.append((x + noise_x, y + noise_y))

        # Create the Shapely Polygon object and add it to our list
        square = Polygon(base_corners)
        _polygons.append(square)
        _polygon_names.append(f"v{i + 1}")

        # # Create the Shapely Polygon object
        # irregular_square = Polygon(irregular_corners)
        #
        # _polygons.append(irregular_square)
        # _polygon_names.append(f"v{i + 1}")

    # for el in polygons:
    #   display(el)

    logger.debug("-" * 1000)
    logger.debug(_polygons)
    logger.debug("-" * 1000)

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

    # # add noise to the lines
    # _noise = np.random.normal(0, scale, size=_lines.shape)
    # _lines += _noise

    # check validity

    expected = {
        'v1': ['v3', 'v2', 'v4'],
        'v2': ['v3', 'v1', 'v4'],
        'v3': ['v1', 'v2', 'v4'],
        'v4': ['v2', 'v3', 'v1']
    }

    util = LinePolygonTreeQueryUtil(
        polygons=_polygons,
        lines=_lines,
        line_names=_lines_names,
        polygon_names=_polygon_names
    )

    res_dict = util.line_polygon_mapping

    for key in res_dict:
        if sorted(res_dict[key]) != sorted(expected[key]):
            logger.debug(res_dict[key])
            logger.debug(expected[key])

            logger.debug(util.line_points)
            logger.debug(util.polygons)

            raise Exception(f"{key} not in {expected}")

    logger.debug("Valid")
