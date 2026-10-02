# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from collections import defaultdict
from typing import Dict, List, Set
from xml.etree import ElementTree as ET

# Third-party imports.
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import error

# Microdrop utils imports.
from microdrop_utils.shapely_helpers import (
    draw_polygons_and_line,
    sort_polygon_indices_along_line,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


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

    def __init__(
        self, polygons: List[Polygon], lines: np.ndarray, polygon_names: List[str]
    ):
        """
        Initializes the finder with geometric and naming data.

        Args:
            polygons: A list of shapely.geometry.Polygon objects.
            lines: A NumPy array, with shape (N, 4) representing N lines with
                endpoints [x1, y1, x2, y2].
            polygon_names: A list of names corresponding to the polygons by index.
        """
        if not (len(polygons) == len(polygon_names)):
            raise ValueError("Length of polygons and polygon_names must be the same.")

        self.polygons = polygons
        self.polygon_names = polygon_names
        self.lines = [LineString(line.reshape((2, 2))) for line in lines]

    def get_polygon_neighbours(
        self, max_attempts: int = 10, buffer_factor: float = 128.0
    ) -> Dict[str, List[str]]:
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
            # The STRtree must be rebuilt in each iteration because the polygon
            # geometries change.
            tree = STRtree(current_polygons)

            # Query the tree to find which lines intersect which polygons.
            # Returns a 2D array: [line_indices, polygon_indices]
            query_result = tree.query(self.lines, predicate="intersects")

            line_indices, counts = np.unique(query_result[0], return_counts=True)

            # Success is when every single line is found exactly twice.
            all_lines_found = len(line_indices) == len(self.lines)
            all_lines_have_two_neighbors = np.all(counts == 2)

            if all_lines_found and all_lines_have_two_neighbors:
                logger.debug(
                    f"SUCCESS: Found solution on attempt {attempt + 1}/{max_attempts}."
                )
                return self._build_neighbor_map(query_result)

            # --- If not successful, prepare for the next attempt ---
            logger.debug(
                f"Attempt {attempt + 1}/{max_attempts} failed. Buffering polygons "
                f"and retrying buffer factor ~ {buffer_factor / (attempt + 1)}."
            )
            # Buffer each polygon by a small amount relative to its area
            current_polygons = [
                poly.buffer(poly.area / buffer_factor) for poly in current_polygons
            ]

        ###### Check if we can proceed with looser conditions #######
        logger.warning(
            f"Could not find a solution where each line intersects exactly 2 polygons "
            f"after {max_attempts} attempts."
        )

        if np.all(counts >= 2):
            logger.warning(
                "Proceeding with solution taking first and last polygon intersected "
                "by line"
            )
            return self._build_neighbor_map(query_result)

        ##### Looser conditions failed, raise error: should have a fallback
        ##### method in place to handle this
        raise AlgorithmError(
            "Could not find a solution where each line intersects at least 2 polygons "
        )

    def _build_neighbor_map(self, query_result: np.ndarray) -> Dict[str, List[str]]:
        """Build the final neighbor dictionary from the query results."""
        # Use a defaultdict or a set for easier adding
        neighbours_map: Dict[str, Set[str]] = {
            name: set() for name in self.polygon_names
        }

        # Group polygon indices by their corresponding line index
        for line_idx in range(len(self.lines)):
            # Get the indices of polygons that intersected with this line
            intersecting_poly_indices = query_result[1, query_result[0] == line_idx]

            # if more than 2 polygons found intersecting, only take polygons at
            # line start and end points: sort the polygon indices by the distance
            # of their polygon to the line start
            # then we take the first and last elements of the sorted list
            if len(intersecting_poly_indices) > 2:
                try:
                    intersecting_poly_indices = sort_polygon_indices_along_line(
                        line=self.lines[line_idx],
                        polygons=self.polygons,
                        indices=intersecting_poly_indices,
                    )

                except Exception as e:
                    import tempfile
                    import uuid
                    from pathlib import Path

                    # Create a unique temp filename
                    # utilizing UUID to ensure no file conflicts
                    temp_path = tempfile.gettempdir() / Path(
                        f"poly_debug_{uuid.uuid4().hex[:8]}.png"
                    )

                    fig, ax = draw_polygons_and_line(
                        np.array(self.polygons)[intersecting_poly_indices],
                        self.lines[line_idx],
                        index_labels=list(intersecting_poly_indices),
                    )

                    # 1. Save the figure
                    fig.tight_layout()
                    ax.title.set_text("")
                    fig.savefig(temp_path)

                    # 2. Log the error to your backend/console
                    logger.error(
                        f"Error: {e}. Saving debug plot to {temp_path}. Proceeding "
                        "with random endpoints...",
                        exc_info=True,
                    )

                    # 3. Format the polygon list for the report
                    # Added a header and newlines for cleaner HTML formatting
                    polygons_str = "<br><br>".join(
                        [
                            f"<b>{idx}</b>: {self.polygons[idx]}"
                            for idx in intersecting_poly_indices
                        ]
                    )

                    # 4. Construct the URI
                    uri = temp_path.as_uri()

                    debug_plot = (
                        f"<b>Debug Plot</b>:<br>"
                        f"<a href='{uri}' target='_blank'>"
                        f"  <img src='{uri}' alt='Debug Plot' style='max-width:50%; "
                        "max-height: 50%; border:1px solid #ccc; cursor:zoom-in;'>"
                        f"</a><br>"
                        f"<small>(Click image to maximize)</small>"
                    )

                    # 5. Send the error report
                    error(
                        None,
                        title="Device Loading Error",
                        message=(
                            f"<b>Error</b>: {e}. Proceeding with random polygon "
                            "endpoints...<br><br>"
                            f"{debug_plot}"
                        ),
                        detail=f"<b>Affected Line</b>: {line_idx}: "
                        f"{self.lines[line_idx]}<br><br>"
                        f"<b>Affected Polygons</b>:<br>{polygons_str} <br><br>",
                    )

            # Just take first and last ones -- endpoint polygons.
            poly1_idx, poly2_idx = (
                intersecting_poly_indices[0],
                intersecting_poly_indices[-1],
            )

            name1 = self.polygon_names[poly1_idx]
            name2 = self.polygon_names[poly2_idx]

            # Register the neighbor relationship symmetrically
            neighbours_map[name1].add(name2)
            neighbours_map[name2].add(name1)

        # Convert the sets to lists for the final output
        return {key: list(val) for key, val in neighbours_map.items()}


def channels_to_svg(
    old_filename, new_filename, electrode_ids_channels_map: dict[str, int], scale: float
):
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
        element_id = electrode.attrib.get("id")
        if element_id not in electrode_ids_channels_map:
            continue
        channel = electrode_ids_channels_map[element_id]
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
    from matplotlib import pyplot as plt

    # func to plot shapely polygons and lines.
    def plot_shapes_lines(polygons, lines):
        # Create a new plot
        fig, ax = plt.subplots()

        # Plot the polygons with a semi-transparent blue color
        for poly in polygons:
            x, y = poly.exterior.xy
            ax.fill(x, y, alpha=0.5, fc="b", ec="none")

        # Plot the line with a contrasting solid red color and a thicker line width
        for line in lines:
            x, y = line.xy
            ax.plot(x, y, color="red", linewidth=3, solid_capstyle="round")

        # Set plot aspect ratio and labels for better visualization
        ax.set_aspect("equal", "box")
        ax.set_title("Shapely Polygons and Lines")
        plt.xlabel("X-axis")
        plt.ylabel("Y-axis")
        plt.grid(True)

        # Show the plot
        plt.show()

    # vertices for a square polygon
    v1 = [1.0, 1.0]
    v2 = [2.0, 1.0]
    v3 = [2.0, 0.0]
    v4 = [1.0, 0.0]

    _centers = np.array([v1, v2, v3, v4])  # square. points sep by 1 unit.

    _lines_names = ["v1-v2", "v2-v3", "v3-v4", "v1-v4", "v1-v3", "v2-v4"]

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
            (cx - h, cy + h),  # Top-left
        ]

        # Perturb each corner by adding random noise
        irregular_corners = []
        irregularity = (
            side_length / 4
        )  # How much the corners can be moved. 0=perfect square.
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
    _lines = np.array([v1 + v2, v2 + v3, v3 + v4, v4 + v1, v1 + v3, v2 + v4])

    scale = side_length / 7

    # # add noise to the lines
    _noise = np.random.normal(0, scale, size=_lines.shape)
    _lines += _noise

    _lines_strs = [LineString(points) for points in _lines.reshape(-1, 2, 2)]

    # check validity

    expected = {
        "v1": ["v3", "v2", "v4"],
        "v2": ["v3", "v1", "v4"],
        "v3": ["v1", "v2", "v4"],
        "v4": ["v2", "v3", "v1"],
    }

    plot_shapes_lines(polygons=_polygons, lines=_lines_strs)

    util = PolygonNeighborFinder(
        polygons=_polygons,
        lines=_lines,
        polygon_names=_polygon_names,
    )

    expected = {
        "v1": ["v3", "v2", "v4"],
        "v2": ["v3", "v1", "v4"],
        "v3": ["v2", "v4", "v1"],
        "v4": ["v2", "v3", "v1"],
    }

    map = util.get_polygon_neighbours(max_attempts=1000, buffer_factor=-(2**5))

    for el in map:
        if sorted(map[el]) != sorted(expected[el]):
            print("FAIL")
            raise Exception(f"{map[el]} is not the expected map: {expected}")

    print("*" * 1000)
    print("PASS")
    print("*" * 1000)
