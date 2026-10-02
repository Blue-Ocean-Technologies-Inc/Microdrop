# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free device-SVG geometry: flatten the Device layer's electrode paths
into vertex arrays (in mm) and shapely polygons.

Shared so any plugin can draw a device's electrodes — the device viewer
builds its model from it, the image viewer its alignment outline —
without importing the device viewer's internals.
"""

# Standard library imports.
import re
from pathlib import Path
from typing import Dict, List, Union
from xml.etree import ElementTree as ET

# Third-party imports.
import numpy as np
from shapely.geometry import Polygon
from svg.path import Arc, CubicBezier, QuadraticBezier, parse_path

# Enthought library imports.
from traits.api import Array, HasTraits, Instance

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Vertices sampled along each curved path segment (arcs, Béziers) when a
#: path is flattened to a polygon; 24/segment keeps an Inkscape circle
#: (two Arc segments) within ~0.2% radial error of the true curve.
CURVE_SEGMENT_SAMPLES = 24

DPI = 96
INCH_TO_MM = 25.4


def pixels_to_mm(pixels):
    return pixels * INCH_TO_MM / DPI


def points_to_mm(points):
    pixels = points * DPI / 72
    return pixels_to_mm(pixels)


def picas_to_mm(picas):
    points = picas * 12
    return points_to_mm(points)


def mm_to_pixels(mm):
    return mm * DPI / INCH_TO_MM


def mm_to_points(mm):
    pixels = mm_to_pixels(mm)
    return pixels * 72 / DPI


def mm_to_picas(mm):
    points = mm_to_points(mm)
    return points / 12


inkscape_units = ["mm", "cm", "pt", "pc", "px"]

_mm_converter_func = {
    "mm": lambda v: v,
    "cm": lambda v: 10 * v,
    "pt": points_to_mm,
    "pc": picas_to_mm,
    "px": pixels_to_mm,
}

_mm_converter_func_inverse = {
    "mm": lambda v: v,
    "cm": lambda v: v / 10,
    "pt": mm_to_points,
    "pc": mm_to_picas,
    "px": mm_to_pixels,
}


def as_valid_polygon(polygon: Polygon) -> Polygon:
    """Return a valid single Polygon for ``polygon``.

    Self-intersecting rings (Inkscape paths whose arc traversals overlap at
    the seam) render fine under SVG's fill rule but break shapely ops.
    ``buffer(0)`` rebuilds a valid geometry; when the crossing splits the
    ring into several lobes (a MultiPolygon), the dominant lobe is the
    electrode body — keep it and log the discarded sliver area.
    """
    if polygon.is_valid:
        return polygon
    repaired = polygon.buffer(0)
    if repaired.geom_type == "MultiPolygon":
        largest = max(repaired.geoms, key=lambda g: g.area)
        dropped = repaired.area - largest.area
        if dropped > 0:
            logger.info(
                f"Self-intersection repair dropped {dropped:.4f} area units "
                f"({dropped / repaired.area:.1%}) of sliver lobes"
            )
        repaired = largest
    return repaired


class ElectrodeData(HasTraits):
    channel = Instance(
        int, allow_none=True
    )  # Int() doesn't seem to follow allow_none for some reason
    path = Array


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

        ### Set unit normalization func to get all values in mm everytime.
        # Pixels when the svg file gives no units, or invalid ones.
        _svg_file_units = "px"
        svg_width, svg_height = self.root.get("width"), self.root.get("height")

        for unit in inkscape_units:
            if unit in svg_width and unit in svg_height:
                _svg_file_units = unit

        self.unit_normalization_func = _mm_converter_func[_svg_file_units]
        self.unit_normalization_func_inverse = _mm_converter_func_inverse[
            _svg_file_units
        ]

    @staticmethod
    def _parse_path_string(d_string: str) -> np.ndarray:
        """
        Robustly parses an SVG path 'd' string into an array of vertex
        coordinates using the original SVG coordinate system.

        Straight segments (Move/Line/Close) contribute their endpoint.
        Curved segments (Arc, cubic/quadratic Bézier) are flattened by
        sampling CURVE_SEGMENT_SAMPLES points along the curve, so shapes
        like Inkscape circles (encoded as two Arc segments) become regular
        polygons instead of degenerate endpoint pairs — downstream shapely
        Polygons then get real areas/centroids/neighbours for them.

        Args:
            d_string: The string from the 'd' attribute of an SVG path.

        Returns:
            A NumPy array of shape (N, 2) with the path's vertex coordinates.
        """
        path = parse_path(d_string)
        points = []
        for segment in path:
            if isinstance(segment, (Arc, CubicBezier, QuadraticBezier)):
                # t=0 is the previous segment's end (already appended);
                # sample up to and including this segment's own end.
                for i in range(1, CURVE_SEGMENT_SAMPLES + 1):
                    point = segment.point(i / CURVE_SEGMENT_SAMPLES)
                    points.append((point.real, point.imag))
            else:
                # The endpoint attribute is a complex number (x + yj)
                end_point = segment.end
                points.append((end_point.real, end_point.imag))
        return np.array(points)

    def _update_bounding_box(self, points_list: List[np.ndarray]):
        """Calculate and update the bounding box from a list of point arrays."""
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
        transform_str = element.attrib.get("transform", "").replace(" ", "")
        match = re.search(
            r"translate\((?P<x>[-\d.]+),(?P<y>[-\d.]+)\)", transform_str.lower()
        )
        # Apply the Y transform directly, without negation
        transform = (
            np.array([float(match.group("x")), float(match.group("y"))])
            if match
            else np.array([0, 0])
        )
        return transform

    def svg_to_electrodes(self, group_element: ET.Element) -> Dict[str, ElectrodeData]:
        """
        Converts path elements within an SVG group into an electrode dictionary,
        applying transforms, scaling, and calculating the bounding box.
        """
        electrodes: Dict[str, ElectrodeData] = {}
        all_electrode_paths = []

        # Parse the 'transform' attribute of the parent group
        transform = self.get_transform(group_element)

        for element in group_element:
            d_string = element.attrib.get("d", "")
            element_id = element.attrib.get("id")

            if d_string and element_id:
                # Parse the path using the original coordinate system
                path_points = self._parse_path_string(d_string)

                # Repair self-intersecting rings AT THE SOURCE so the
                # rendered electrode (ElectrodeView fills this path) and the
                # geometry math (shapely polygons) agree on one shape. Left
                # raw, Qt's default odd-even fill rule unfills the seam
                # overlap — a visible notch the SVG's nonzero fill rule
                # (Inkscape) never shows.
                if len(path_points) >= 3:
                    try:
                        ring = Polygon(path_points)
                        if not ring.is_valid:
                            path_points = np.array(
                                as_valid_polygon(ring).exterior.coords
                            )
                    except Exception as e:
                        logger.warning(
                            f"Could not validity-check path '{element_id}': {e}"
                        )

                # Apply all transformations: translation and then scaling
                transformed_path = self.unit_normalization_func(path_points + transform)

                channel_str = element.attrib.get("data-channels")
                electrodes[element_id] = ElectrodeData(
                    channel=int(channel_str) if channel_str is not None else None,
                    path=transformed_path,
                )
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
            group_element: The elements within an SVG group containing the
                connection lines / paths.

        Returns:
            A np.array of connection line records, where each record is:
            [<id>, <x1>, <y1>, <x2>, <y2>]. This will be in mm with its group's
            translation applied as found from the svg.
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
            tag = element.tag.split("}")[-1]

            # --- Process <line> elements ---
            if tag == "line":
                try:
                    x1 = float(element.attrib["x1"])
                    y1 = float(element.attrib["y1"])
                    x2 = float(element.attrib["x2"])
                    y2 = float(element.attrib["y2"])
                    lines.append([x1, y1, x2, y2])
                except KeyError:
                    logger.warning(
                        f"Warning: Skipping malformed <line> element '{element}'."
                    )

            # --- Process <path> elements using svg.path ---
            elif tag == "path":
                d_string = element.attrib.get("d")
                if d_string:
                    try:
                        path_obj = parse_path(d_string)
                        if path_obj:
                            # The start point is the start of the first segment
                            start_point = path_obj[0].start
                            # The end point is the end of the last segment
                            end_point = path_obj[-1].end

                            lines.append(
                                [
                                    start_point.real,  # x1
                                    start_point.imag,  # y1
                                    end_point.real,  # x2
                                    end_point.imag,  # y2
                                ]
                            )

                    except (IndexError, ValueError) as e:
                        logger.warning(
                            f"Warning: Could not parse <path> '{element}': {e}"
                        )

        if len(lines) == 0:
            return None

        # convert list to np array to easily apply tranformations
        lines = np.array(lines)
        lines = (lines.reshape(-1, 2) + transform).reshape(
            -1, 4
        )  # apply translation to start and end points
        return self.unit_normalization_func(lines)


def is_device_layer(element: ET.Element) -> bool:
    """Whether ``element`` is the SVG's Device layer (matched on any
    attribute value, case-insensitively — Inkscape keeps it in the label)."""
    return "device" in [value.casefold() for value in element.attrib.values()]


def device_electrode_polygons(svg_path) -> List[Polygon]:
    """The electrode polygons of the device SVG at ``svg_path``, in mm and
    SVG orientation (y down); [] when it has no Device layer."""
    processor = SVGProcessor(filename=str(svg_path))
    polygons = []

    for child in processor.root:
        if not is_device_layer(child):
            continue

        for electrode_id, electrode in processor.svg_to_electrodes(child).items():
            coords = electrode.path.reshape(-1, 2)

            # A path that flattens to under three vertices encloses nothing.
            if len(coords) < 3:
                logger.debug(f"Skipping degenerate electrode path '{electrode_id}'")
                continue

            polygons.append(Polygon(coords))

        break

    return polygons


def list_device_svgs(directory) -> List[Path]:
    """The device SVG files directly inside ``directory``, sorted by name;
    [] when it is unset or not a directory."""
    if not directory or not Path(directory).is_dir():
        return []

    svg_files = [
        path for path in Path(directory).iterdir() if path.suffix.lower() == ".svg"
    ]

    return sorted(svg_files, key=lambda path: path.name.casefold())
