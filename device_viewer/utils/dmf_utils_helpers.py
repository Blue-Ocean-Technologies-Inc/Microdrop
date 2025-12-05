import re
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from shapely.geometry import Polygon, LineString
from shapely.strtree import STRtree
from collections import defaultdict
from typing import List, Dict, Set, TypedDict, Optional, Any, Union

from svg.path import parse_path

from logger.logger_service import get_logger
from microdrop_utils.shapely_helpers import sort_polygon_indices_along_line

logger = get_logger(__name__, "INFO")


DPI=96
INCH_TO_MM = 25.4
DOTS_TO_MM = INCH_TO_MM / DPI

class AlgorithmError(Exception):
    """Raised when the algorithm fails to find a valid solution."""
    pass


class PolygonNeighborFinder:
    """
    Finds neighboring polygons based on intersections with a given set of lines.

    This class uses an STRtree for efficient spatial querying. It identifies pairs
    of polygons that are considered "neighbors" because a line segment intersects
    both of them.
    """

    def __init__(self, polygons: List[Polygon], lines: np.ndarray, polygon_names: List[str]):
        """
        Initializes the finder with geometric and naming data.

        Args:
            polygons: A list of shapely.geometry.Polygon objects.
            lines: A NumPy array, with shape (N, 4) representing N lines with endpoints [x1, y1, x2, y2].
            polygon_names: A list of names corresponding to the polygons by index.
        """
        if not (len(polygons) == len(polygon_names)):
            raise ValueError("Length of polygons and polygon_names must be the same.")

        self.polygons = polygons
        self.polygon_names = polygon_names
        self.lines = [LineString(line.reshape((2, 2))) for line in lines]

    def get_polygon_neighbours(self, max_attempts: int = 10, buffer_factor: float = 128.0) -> Dict[str, List[str]]:
        """
        Attempts to find exactly two intersecting polygons for each line.

        If an immediate intersection query doesn't yield two polygons per line, this
        method iteratively buffers the polygons and retries the query until the
        condition is met or max_attempts is reached.

        Args:
            max_attempts: The maximum number of times to buffer and retry the query.
            buffer_factor: A factor used to determine the buffer size, relative to
                           the polygon's area.

        Returns:
            A dictionary mapping each polygon name to a list of its neighbors.

        Raises:
            ValueError: If a solution cannot be found within the given attempts.
        """
        # Start with the original polygons
        current_polygons = self.polygons

        for attempt in range(max_attempts):
            # The STRtree must be rebuilt in each iteration because the polygon geometries change.
            tree = STRtree(current_polygons)

            # Query the tree to find which lines intersect which polygons.
            # Returns a 2D array: [line_indices, polygon_indices]
            query_result = tree.query(self.lines, predicate="intersects")

            line_indices, counts = np.unique(query_result[0], return_counts=True)

            # Success is when every single line is found exactly twice.
            all_lines_found = len(line_indices) == len(self.lines)
            all_lines_have_two_neighbors = np.all(counts == 2)

            if all_lines_found and all_lines_have_two_neighbors:
                logger.debug(f"SUCCESS: Found solution on attempt {attempt + 1}/{max_attempts}.")
                return self._build_neighbor_map(query_result)

            # --- If not successful, prepare for the next attempt ---
            logger.debug(
                f"Attempt {attempt + 1}/{max_attempts} failed. Buffering polygons and retrying buffer factor ~ {buffer_factor / (attempt + 1)}."
            )
            # Buffer each polygon by a small amount relative to its area
            current_polygons = [poly.buffer(poly.area / buffer_factor) for poly in current_polygons]

        ###### Check if we can proceed with looser conditions #######
        logger.warning(f"Could not find a solution where each line intersects exactly 2 polygons "
            f"after {max_attempts} attempts.")

        if np.all(counts >= 2):
            logger.warning("Proceeding with solution taking first and last polygin intersected by line")
            return self._build_neighbor_map(query_result)

        ##### Looser conditions failed, raise error: should have a fallback method in place to handle this
        raise AlgorithmError(
            f"Could not find a solution where each line intersects at least 2 polygons "
        )

    def _build_neighbor_map(self, query_result: np.ndarray) -> Dict[str, List[str]]:
        """Helper method to construct the final neighbor dictionary from query results."""
        # Use a defaultdict or a set for easier adding
        neighbours_map: Dict[str, Set[str]] = {name: set() for name in self.polygon_names}

        # Group polygon indices by their corresponding line index
        for line_idx in range(len(self.lines)):
            # Get the indices of polygons that intersected with this line
            intersecting_poly_indices = query_result[1, query_result[0] == line_idx]

            # if more than 2 polygons found intersecting, only take polygons at line start and end points
            # do this by sorting polygon indices by distance of corresponding polygon to line start
            # then we take the first and last elements of the sorted list
            if len(intersecting_poly_indices) > 2:
                intersecting_poly_indices = sort_polygon_indices_along_line(line=self.lines[line_idx],
                                                                            polygons=self.polygons,
                                                                            indices=list(intersecting_poly_indices))

            # Just take first and last ones -- endpoint polygons.
            poly1_idx, poly2_idx = intersecting_poly_indices[0], intersecting_poly_indices[-1]

            name1 = self.polygon_names[poly1_idx]
            name2 = self.polygon_names[poly2_idx]

            # Register the neighbor relationship symmetrically
            neighbours_map[name1].add(name2)
            neighbours_map[name2].add(name1)

        # Convert the sets to lists for the final output
        return {key: list(val) for key, val in neighbours_map.items()}


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


class ElectrodeDict(TypedDict):
    channel: int
    path: np.ndarray # NDArray[Shape['*, 1, 1'], Float]

class SVGProcessor:
    """
    Parses SVG files to extract path data for electrodes and connections,
    respecting the original SVG coordinate system (top-left origin).
    """
    def __init__(self, filename: str):
        """Initializes the processor by loading and parsing an SVG file."""
        tree = ET.parse(filename)
        self.root = tree.getroot()
        # Bounding box attributes are initialized
        self.min_x = self.min_y = self.max_x = self.max_y = None

    @staticmethod
    def _parse_path_string(d_string: str) -> np.ndarray:
        """
        Robustly parses an SVG path 'd' string into an array of vertex
        coordinates using the original SVG coordinate system.

        Args:
            d_string: The string from the 'd' attribute of an SVG path.

        Returns:
            A NumPy array of shape (N, 2) with the path's vertex coordinates.
        """
        path = parse_path(d_string)
        points = []
        for segment in path:
            # The endpoint attribute is a complex number (x + yj)
            end_point = segment.end
            # Extract real (x) and imag (y) parts directly without flipping
            points.append((end_point.real, end_point.imag))
        return np.array(points)

    def _update_bounding_box(self, points_list: List[np.ndarray]):
        """Efficiently calculates and updates the bounding box from a list of point arrays."""
        if not points_list:
            return
        # Combine all points into a single large array for one-pass calculation
        all_points = np.vstack(points_list)
        self.min_x, self.min_y = all_points.min(axis=0)
        self.max_x, self.max_y = all_points.max(axis=0)

    def get_bounding_box(self):
        return self.min_x, self.min_y, self.max_x, self.max_y

    @staticmethod
    def get_transform(element: ET.Element) -> np.ndarray:
        # Parse the 'transform' attribute of the parent group
        transform_str = element.attrib.get('transform', '').replace(' ', '')
        match = re.search(r"translate\((?P<x>[-\d.]+),(?P<y>[-\d.]+)\)",
                          transform_str.lower())
        # Apply the Y transform directly, without negation
        transform = np.array([float(match.group('x')), float(match.group('y'))]) if match else np.array([0, 0])
        return transform

    def svg_to_electrodes(self, group_element: ET.Element) -> Dict[str, ElectrodeDict]:
        """
        Converts path elements within an SVG group into an electrode dictionary,
        applying transforms, scaling, and calculating the bounding box.
        """
        electrodes: Dict[str, ElectrodeDict] = {}
        all_electrode_paths = []

        # Parse the 'transform' attribute of the parent group
        transform = self.get_transform(group_element)

        for element in group_element:
            d_string = element.attrib.get("d", "")
            element_id = element.attrib.get("id")

            if d_string and element_id:
                # Parse the path using the original coordinate system
                path_points = self._parse_path_string(d_string)

                # Apply all transformations: translation and then scaling
                transformed_path = (path_points + transform) * DOTS_TO_MM

                channel_str = element.attrib.get('data-channels')
                electrodes[element_id] = {
                    'channel': int(channel_str) if channel_str is not None else None,
                    'path': transformed_path
                }
                all_electrode_paths.append(transformed_path)
            else:
                logger.debug(f"Skipping {element} due lack of elements.")

        self._update_bounding_box(all_electrode_paths)
        return electrodes

    def extract_connections(self, group_element: ET.Element) -> Union[np.ndarray, None]:
        """
        Extracts start and end coordinates from <line> and <path> elements
        within a specific Inkscape layer of an SVG file.

        Args:
            group_element: The elements within an SVG group containing the connection lines / paths.

        Returns:
            A np.array of connection line records, where each record is: [<id>, <x1>, <y1>, <x2>, <y2>].
            This will be in mm with its group's translation applied as found from the svg.
        """

        if not len(group_element):
            logger.debug(f"Skipping {group_element} due to no elements.")
            return None

        # List to hold records of form: `[<x1>, <y1>, <x2>, <y2>]`.
        lines = []

        # Parse the 'transform' attribute of the parent group
        transform = self.get_transform(group_element)

        # 2. Iterate through all elements in the layer
        for element in group_element:
            # Extract the tag name without the namespace prefix
            tag = element.tag.split('}')[-1]

            # --- Process <line> elements ---
            if tag == 'line':
                try:
                    x1 = float(element.attrib['x1'])
                    y1 = float(element.attrib['y1'])
                    x2 = float(element.attrib['x2'])
                    y2 = float(element.attrib['y2'])
                    lines.append([x1, y1, x2, y2])
                except KeyError:
                    logger.warning(f"Warning: Skipping malformed <line> element '{element}'.")

            # --- Process <path> elements using svg.path ---
            elif tag == 'path':
                d_string = element.attrib.get('d')
                if d_string:

                    try:
                        path_obj = parse_path(d_string)
                        if path_obj:

                            # The start point is the start of the first segment
                            start_point = path_obj[0].start
                            # The end point is the end of the last segment
                            end_point = path_obj[-1].end

                            lines.append([
                                start_point.real,  # x1
                                start_point.imag,  # y1
                                end_point.real,  # x2
                                end_point.imag  # y2
                            ])

                    except (IndexError, ValueError) as e:
                        logger.warning(f"Warning: Could not parse <path> '{element}': {e}")

        if len(lines) == 0:
            return None

        # convert list to np array to easily apply tranformations
        lines = np.array(lines)
        lines = (lines.reshape(-1, 2) + transform).reshape(-1,4) # apply translation to start and end points
        return lines * DOTS_TO_MM



if __name__ == "__main__":

    from matplotlib import pyplot as plt

    # func to plot shapely polygons and lines.
    def plot_shapes_lines(polygons, lines):
        # Create a new plot
        fig, ax = plt.subplots()

        # Plot the polygons with a semi-transparent blue color
        for poly in polygons:
            x, y = poly.exterior.xy
            ax.fill(x, y, alpha=0.5, fc='b', ec='none')

        # Plot the line with a contrasting solid red color and a thicker line width
        for line in lines:
            x, y = line.xy
            ax.plot(x, y, color='red', linewidth=3, solid_capstyle='round')

        # Set plot aspect ratio and labels for better visualization
        ax.set_aspect('equal', 'box')
        ax.set_title('Shapely Polygons and Lines')
        plt.xlabel("X-axis")
        plt.ylabel("Y-axis")
        plt.grid(True)

        # Show the plot
        plt.show()


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

        # Perturb each corner by adding random noise
        irregular_corners = []
        irregularity = side_length / 4  # How much the corners can be moved. 0=perfect square.
        for x, y in base_corners:
            noise_x = np.random.uniform(-irregularity, irregularity)
            noise_y = np.random.uniform(-irregularity, irregularity)
            irregular_corners.append((x + noise_x, y + noise_y))

        # Create the Shapely Polygon object and add it to our list
        # square = Polygon(base_corners)
        # _polygons.append(square)
        # _polygon_names.append(f"v{i + 1}")

        # Create the Shapely Polygon object
        irregular_square = Polygon(irregular_corners)

        _polygons.append(irregular_square)
        _polygon_names.append(f"v{i + 1}")

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

    scale = side_length / 7

    # # add noise to the lines
    _noise = np.random.normal(0, scale, size=_lines.shape)
    _lines += _noise

    _lines_strs = [LineString(points) for points in _lines.reshape(-1, 2, 2)]

    # check validity

    expected = {
        'v1': ['v3', 'v2', 'v4'],
        'v2': ['v3', 'v1', 'v4'],
        'v3': ['v1', 'v2', 'v4'],
        'v4': ['v2', 'v3', 'v1']
    }

    plot_shapes_lines(polygons=_polygons,
                      lines=_lines_strs)

    util = PolygonNeighborFinder(
        polygons=_polygons,
        lines=_lines,
        polygon_names=_polygon_names,
    )



    expected = {'v1': ['v3', 'v2', 'v4'], 'v2': ['v3', 'v1', 'v4'], 'v3': ['v2', 'v4', 'v1'],
                'v4': ['v2', 'v3', 'v1']}

    map = util.get_polygon_neighbours(max_attempts=1000, buffer_factor=-2**5)

    for el in map:
        if sorted(map[el]) != sorted(expected[el]):
            print("FAIL")
            raise Exception(f"{map[el]} is not the expected map: {expected}")

    print("*" * 1000)
    print("PASS")
    print("*" * 1000)


